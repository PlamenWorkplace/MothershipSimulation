import simpy
import random
from collections import deque
from collections import defaultdict

# === Parameters ===
NEIGHBORHOODS = [
    "Tongelre", "T'Hofke", "Woensel", "Stratum", "Genderbeemd/Hanevoet",
    "Strijp-S", "Blixembosch-Oost", "Vaartbroek/Eckart", "City Centre",
    "Rozenknopje", "Oud-Woensel"
]

BUS_CAPACITY = 10
STOP_TIME = 1
TRIP_INTERVAL = 5
SIM_TIME = 960  # minutes (6:00 to 22:00)
PASSENGER_RATE = 0.2  # Poisson arrival rate per minute per stop

PEAK_HOURS = [(60, 180), (600, 720)]  # 07:00–10:00 and 16:00–19:00

# === Queues and metrics ===
stop_queues = {stop: deque() for stop in NEIGHBORHOODS}
all_passengers = []
served_passengers = []
missed_passengers = []


# === Passenger Process ===
def get_current_rate(time):
    # Higher arrival rate during peak, lower off-peak
    if 60 <= time < 180 or 600 <= time < 720:
        return 0.35  # peak demand
    else:
        return 0.15  # off-peak demand

def generate_passengers(env, stop_name, stop_queues):
    while True:
        current_time = env.now
        current_rate = get_current_rate(current_time)
        yield env.timeout(random.expovariate(current_rate))
        destination = random.choice([s for s in NEIGHBORHOODS if s != stop_name])
        passenger = {
            "origin": stop_name,
            "destination": destination,
            "arrival_time": env.now
        }
        stop_queues[stop_name].append(passenger)
        all_passengers.append(passenger)



# === Mothership Process ===
def mothership(env, stop_queues, bus_id, shutdown_flag):
    while True:
        if shutdown_flag["stop"]:
            break  # Exit loop — kill this bus

        onboard = []

        for stop in NEIGHBORHOODS:
            # Drop-off
            drop_offs = [p for p in onboard if p['destination'] == stop]
            for p in drop_offs:
                onboard.remove(p)

            # Pick-up
            queue = stop_queues[stop]
            while queue and len(onboard) < BUS_CAPACITY:
                passenger = queue.popleft()
                passenger['pickup_time'] = env.now
                served_passengers.append(passenger)
                onboard.append(passenger)

            yield env.timeout(STOP_TIME)

        # Wait before restarting trip
        yield env.timeout(TRIP_INTERVAL)


# === Dynamic Bus Launch Scheduler ===
def bus_scheduler(env, stop_queues):
    active_buses = []

    def launch_buses(num, label_prefix):
        for i in range(num):
            shutdown_flag = {"stop": False}
            bus_name = f"{label_prefix}-{i+1}"
            proc = env.process(mothership(env, stop_queues, bus_name, shutdown_flag))
            active_buses.append((proc, shutdown_flag))

    # Initially off-peak
    launch_buses(4, "OffPeak")

    yield env.timeout(60)  # 06:00 → 07:00

    # 07:00–10:00 Peak → 6 buses
    launch_buses(2, "Peak-AM")  # Add 2 more to make 6 total
    yield env.timeout(180)  # 07:00–10:00

    # At 10:00, mark 2 buses for shutdown
    removed = 0
    for proc, flag in active_buses:
        if removed < 2:
            flag["stop"] = True
            removed += 1

    yield env.timeout(240)  # 10:00–16:00 (off-peak)

    # 16:00–19:00 Peak → 6 buses
    launch_buses(2, "Peak-PM")
    yield env.timeout(180)  # 16:00–19:00

    # Back to off-peak for last 3 hours
    yield env.timeout(180)  # 19:00–22:00


# === SimPy Environment ===
env = simpy.Environment()

# Start passenger generators
for stop in NEIGHBORHOODS:
    env.process(generate_passengers(env, stop, stop_queues))

# Start bus scheduler
env.process(bus_scheduler(env, stop_queues))

# Run simulation
env.run(until=SIM_TIME)

# === Final Reporting ===
for queue in stop_queues.values():
    missed_passengers.extend(queue)

# Categorize passengers by time
def is_peak_minute(t):
    return (60 <= t < 180) or (600 <= t < 720)

# Aggregation variables
peak_created = peak_served = peak_missed = 0
offpeak_created = offpeak_served = offpeak_missed = 0
peak_wait_times = []
offpeak_wait_times = []

for p in all_passengers:
    if is_peak_minute(p["arrival_time"]):
        peak_created += 1
    else:
        offpeak_created += 1

for p in served_passengers:
    wait = p['pickup_time'] - p['arrival_time']
    if is_peak_minute(p["arrival_time"]):
        peak_served += 1
        peak_wait_times.append(wait)
    else:
        offpeak_served += 1
        offpeak_wait_times.append(wait)

for p in missed_passengers:
    if is_peak_minute(p["arrival_time"]):
        peak_missed += 1
    else:
        offpeak_missed += 1

# === Per-Neighborhood Stats ===
neighborhood_stats = {
    stop: {
        'created': 0,
        'served': 0,
        'missed': 0,
        'wait_times': []
    }
    for stop in NEIGHBORHOODS
}

for p in all_passengers:
    neighborhood_stats[p['origin']]['created'] += 1

for p in served_passengers:
    origin = p['origin']
    wait = p['pickup_time'] - p['arrival_time']
    neighborhood_stats[origin]['served'] += 1
    neighborhood_stats[origin]['wait_times'].append(wait)

for p in missed_passengers:
    origin = p['origin']
    neighborhood_stats[origin]['missed'] += 1

# === Print Neighborhood Summary ===
print("\n--- Per-Neighborhood Summary ---")
for stop in NEIGHBORHOODS:
    data = neighborhood_stats[stop]
    avg_wait = (sum(data['wait_times']) / len(data['wait_times'])) if data['wait_times'] else 0
    print(f"{stop:25} | Created: {data['created']:4} | Served: {data['served']:4} | Missed: {data['missed']:3} | Avg Wait: {avg_wait:.2f} min")


# === Print Detailed Report ===
print("\n=== SIMULATION RESULTS ===")
print(f"Total passengers created:     {len(all_passengers)}")
print(f"Total passengers served:      {len(served_passengers)}")
print(f"Total passengers missed:      {len(missed_passengers)}")

print("\n--- Peak Hours (07:00–10:00, 16:00–19:00) ---")
print(f"Passengers created:           {peak_created}")
print(f"Passengers served:            {peak_served}")
print(f"Passengers missed:            {peak_missed}")
print(f"Average wait time:            {sum(peak_wait_times)/len(peak_wait_times):.2f} min" if peak_wait_times else "No data")

print("\n--- Off-Peak Hours ---")
print(f"Passengers created:           {offpeak_created}")
print(f"Passengers served:            {offpeak_served}")
print(f"Passengers missed:            {offpeak_missed}")
print(f"Average wait time:            {sum(offpeak_wait_times)/len(offpeak_wait_times):.2f} min" if offpeak_wait_times else "No data")


