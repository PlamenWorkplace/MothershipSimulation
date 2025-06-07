import math
import simpy
import random
from collections import deque, defaultdict

# === Parameters ===
BLUE_ROUTE = [
    {"stop": "Broekakkerseweg 26", "travel_time_to_next": 10, "expected_daily_passengers": 10},
    {"stop": "Eindhoven, Boutenslaan", "travel_time_to_next": 9, "expected_daily_passengers": 25},
    {"stop": "Eindhoven, Kastelenplein", "travel_time_to_next": 5, "expected_daily_passengers": 35},
    {"stop": "Eindhoven, Donizettilaan", "travel_time_to_next": 6, "expected_daily_passengers": 40},
    {"stop": "Eindhoven, Cederlaan", "travel_time_to_next": 8, "expected_daily_passengers": 30},
    {"stop": "Eindhoven, Piazza", "travel_time_to_next": 8, "expected_daily_passengers": 60},
    {"stop": "Tongelrestraat 276", "travel_time_to_next": 4, "expected_daily_passengers": 20},
]

BLUE_BUS_STOPS = [stop["stop"] for stop in BLUE_ROUTE]

RED_ROUTE = [
    {"stop": "Broekakkerseweg 26", "travel_time_to_next": 1, "expected_daily_passengers": 10},
    {"stop": "Eindhoven, Hageheldlaan", "travel_time_to_next": 4, "expected_daily_passengers": 30},
    {"stop": "Tongelrestraat 392", "travel_time_to_next": 6, "expected_daily_passengers": 40},
    {"stop": "Eindhoven, Thomas A Kempislaan", "travel_time_to_next": 5, "expected_daily_passengers": 25},
    {"stop": "Eindhoven, Heistraat", "travel_time_to_next": 3, "expected_daily_passengers": 20},
    {"stop": "Jan Smitzlaan 20", "travel_time_to_next": 5, "expected_daily_passengers": 30},
    {"stop": "Eindhoven, Gagelstraat", "travel_time_to_next": 3, "expected_daily_passengers": 35},
    {"stop": "Essenstraat 1", "travel_time_to_next": 3, "expected_daily_passengers": 15},
    {"stop": "Johannes van der Waalsweg 39", "travel_time_to_next": 8, "expected_daily_passengers": 20},
    {"stop": "Eindhoven, WoensXL/Genovevalaan", "travel_time_to_next": 6, "expected_daily_passengers": 45},
    {"stop": "Ouverture 228", "travel_time_to_next": 9, "expected_daily_passengers": 50},
    {"stop": "Eindhoven, Wijnpeerstraat", "travel_time_to_next": 0, "expected_daily_passengers": 40},
]

RED_BUS_STOPS = [stop["stop"] for stop in RED_ROUTE]

BUS_CAPACITY = 22  # Updated from demand estimation
SIM_TIME = 960  # minutes (6:00 to 22:00)

# Package delivery parameters
DAILY_PACKAGES = 248  # From demand estimation
ROBOT_CAPACITY = 10  # packages per robot
ROBOT_SPEED = 3  # minutes per delivery
PICKUP_WAIT_TIME = (5, 15)  # min, max wait time for robot pickup

# === Global tracking variables ===
stop_queues_red_route_forward = {stop["stop"]: deque() for stop in RED_ROUTE}
stop_queues_red_route_backward = {stop["stop"]: deque() for stop in RED_ROUTE}
stop_queues_blue_route = {stop["stop"]: deque() for stop in BLUE_ROUTE}
# package_queues = {stop: deque() for stop in NEIGHBORHOODS}
all_passengers = []
served_passengers = []
all_packages = []
delivered_packages = []
missed_packages = []
bus_states = defaultdict(list)

# === Demand weighting by time of day ===
hourly_demand_percent = {
    "06:00–07:00": 0.03,
    "07:00–08:00": 0.09,
    "08:00–09:00": 0.11,
    "09:00–10:00": 0.07,
    "10:00–11:00": 0.05,
    "11:00–12:00": 0.05,
    "12:00–13:00": 0.06,
    "13:00–14:00": 0.06,
    "14:00–15:00": 0.05,
    "15:00–16:00": 0.06,
    "16:00–17:00": 0.08,
    "17:00–18:00": 0.10,
    "18:00–19:00": 0.06,
    "19:00–20:00": 0.04,
    "20:00–21:00": 0.025,
    "21:00–22:00": 0.015,
}

minute_weights = []
for _, percent in hourly_demand_percent.items():
    minute_weights.extend([percent / 60] * 60)

assert len(minute_weights) == 960, f"Expected 960 minutes, got {len(minute_weights)}"


# === Arrival Rate Function ===
def get_passenger_rate(time, stop_name, route):
    """Adjusted per-minute rate using demand weights"""
    if time >= 960:
        return 0

    # Find the stop dict in the route that matches stop_name
    stop_info = next((stop for stop in route if stop["stop"] == stop_name), None)
    if stop_info is None:
        raise ValueError(f"Stop {stop_name} not found in route")

    base_daily_demand = stop_info.get("expected_daily_passengers", 0)
    return base_daily_demand * minute_weights[int(time)]


# def get_package_rate(neighborhood):
#     """Get package generation rate based on neighborhood population"""
#     inhabitants = NEIGHBORHOOD_DATA[neighborhood]["inhabitants"]
#     total_inhabitants = sum(data["inhabitants"] for data in NEIGHBORHOOD_DATA.values())
#     neighborhood_share = inhabitants / total_inhabitants
#     return (DAILY_PACKAGES * neighborhood_share) / SIM_TIME


def generate_passengers(env, stop_name, route, direction=None):
    """Generate passengers with realistic demand patterns"""
    possible_destinations = get_destinations_after_stop(route, stop_name, direction)
    if not possible_destinations:
        return
    while True:
        current_rate = get_passenger_rate(env.now, stop_name, route)
        if current_rate > 0:
            # Convert rate per minute to exponential distribution parameter
            yield env.timeout(random.expovariate(current_rate))
        else:
            yield env.timeout(5)  # Check every 5 minutes if rate is 0
            continue

        # Weighted destination selection based on travel times and attractiveness
        weights = [math.exp(-i) for i in range(len(possible_destinations))]
        destination = random.choices(possible_destinations, weights=weights)[0]
        arrival_time = env.now

        # Passengers arriving after 900 minutes are skipped
        if arrival_time > 900:
            continue

        passenger = {
            "origin": stop_name,
            "destination": destination["stop"],
            "arrival_time": arrival_time
        }
        stop_queues = get_stop_queues(route, direction)
        stop_queues[stop_name].append(passenger)
        all_passengers.append(passenger)


def get_destinations_after_stop(route, stop_name, direction):
    if route == RED_ROUTE and direction == "forward":
        idx = RED_BUS_STOPS.index(stop_name)
        return route[idx + 1 :]
    elif route == RED_ROUTE and direction == "backward":
        idx = RED_BUS_STOPS[::-1] .index(stop_name)
        return route[::-1][idx + 1 :]
    elif route == BLUE_ROUTE:
        idx = BLUE_BUS_STOPS.index(stop_name)
        return route[idx + 1 :] + route[:idx]
    else:
        raise ValueError("Unknown route")


def get_stop_queues(route, direction):
    if route == RED_ROUTE and direction == "forward":
        return stop_queues_red_route_forward
    elif route == RED_ROUTE and direction == "backward":
        return stop_queues_red_route_backward
    elif route == BLUE_ROUTE:
        return stop_queues_blue_route
    else:
        raise ValueError("Unknown route")


# def generate_packages(env, stop_name):
#     """Generate packages for delivery"""
#     package_rate = get_package_rate(stop_name)
#
#     while True:
#         if package_rate > 0:
#             yield env.timeout(random.expovariate(package_rate))
#         else:
#             yield env.timeout(10)  # Check every 10 minutes
#             continue
#
#         # Random destination weighted by population
#         destinations = [s for s in NEIGHBORHOODS if s != stop_name]
#         weights = [NEIGHBORHOOD_DATA[dest]["inhabitants"] for dest in destinations]
#         destination = random.choices(destinations, weights=weights)[0]
#
#         package = {
#             "origin": stop_name,
#             "destination": destination,
#             "creation_time": env.now,
#             "id": len(all_packages)
#         }
#         package_queues[stop_name].append(package)
#         all_packages.append(package)


def mothership_bus(env, bus_id, route, run_duration):
    """Enhanced bus process with realistic travel times and utilization tracking"""
    onboard_passengers = []
    end_time = env.now + run_duration

    last_trip = False
    all_stops = [stop["stop"] for stop in route]
    stops = [stop["stop"] for stop in route]
    direction = "forward"
    try:
        while True:
            stop_queues = get_stop_queues(route, direction)
            for i, current_stop in enumerate(stops):
                if env.now >= end_time:
                    last_trip = True

                # Drop-off passengers
                initial_onboard = len(onboard_passengers)
                drop_offs = [p for p in onboard_passengers if p['destination'] == current_stop]
                for passenger in drop_offs:
                    onboard_passengers.remove(passenger)
                    passenger['dropoff_time'] = env.now
                    passenger['travel_time'] = passenger['dropoff_time'] - passenger['pickup_time']
                    served_passengers.append(passenger)

                # Stop time
                if current_stop == "Broekakkerseweg 26" or current_stop == "Eindhoven, Wijnpeerstraat":
                    if last_trip:
                        return
                    yield env.timeout(random.uniform(5, 10))  # TRIP_INTERVAL between 5 and 10
                else:
                    yield env.timeout(random.uniform(0.5, 1))  # STOP_TIME between 0.5 and 1

                # Pick-up passengers
                picked_up = 0
                if not last_trip:
                    queue = stop_queues[current_stop]
                    while queue and len(onboard_passengers) < BUS_CAPACITY:
                        passenger = queue.popleft()
                        passenger['pickup_time'] = env.now
                        passenger['wait_time'] = passenger['pickup_time'] - passenger['arrival_time']
                        onboard_passengers.append(passenger)
                        picked_up += 1

                # Record bus state
                bus_states[bus_id].append({
                    'time': env.now,
                    'stop': current_stop,
                    'passengers': len(onboard_passengers),
                    'capacity': BUS_CAPACITY,
                    'utilization': len(onboard_passengers) / BUS_CAPACITY,
                    'picked_up': picked_up,
                    'dropped_off': initial_onboard - len(onboard_passengers) + len(drop_offs)
                })

                # Travel to next stop (if not last stop)
                travel_time = route[i]['travel_time_to_next']
                yield env.timeout(travel_time)

            # Reverse direction for red route
            if route is RED_ROUTE:
                if direction == "forward":
                    direction = "backward"
                    stops = all_stops[::-1]
                else:
                    direction = "forward"
                    stops = all_stops[1:]

    except simpy.Interrupt:
        print(f"{bus_id} interrupted at {env.now}")


# def delivery_robot(env, robot_id, origin_stop):
#     """Robot delivery process with pickup by mothership"""
#     packages_carried = []
#
#     # Load packages at origin
#     queue = package_queues[origin_stop]
#     while queue and len(packages_carried) < ROBOT_CAPACITY:
#         package = queue.popleft()
#         package['pickup_time'] = env.now
#         packages_carried.append(package)
#
#     if not packages_carried:
#         return  # No packages to deliver
#
#     # Group packages by destination
#     destinations = defaultdict(list)
#     for package in packages_carried:
#         destinations[package['destination']].append(package)
#
#     # Deliver packages
#     current_location = origin_stop
#     for dest, dest_packages in destinations.items():
#         # Travel to destination
#         travel_time = TRAVEL_TIMES[current_location][dest]
#         yield env.timeout(travel_time)
#         current_location = dest
#
#         # Deliver packages
#         for package in dest_packages:
#             yield env.timeout(ROBOT_SPEED)
#             package['delivery_time'] = env.now
#             package['total_time'] = package['delivery_time'] - package['creation_time']
#             delivered_packages.append(package)
#
#     # Wait for pickup by mothership
#     pickup_wait = random.uniform(*PICKUP_WAIT_TIME)
#     yield env.timeout(pickup_wait)


# def robot_scheduler(env):
#     """Schedule robot deployments based on package demand"""
#     robot_counter = 0
#
#     while True:
#         # Check package queues every 30 minutes
#         yield env.timeout(30)
#
#         for stop in NEIGHBORHOODS:
#             queue_length = len(package_queues[stop])
#             if queue_length >= ROBOT_CAPACITY:
#                 # Deploy robot
#                 robot_counter += 1
#                 env.process(delivery_robot(env, f"Robot-{robot_counter}", stop))


def launch_buses(num, label_prefix, run_duration, route_colour):
    for i in range(num):
        bus_name = f"{label_prefix}-{i+1}"
        route = RED_ROUTE if route_colour == "red" else BLUE_ROUTE
        env.process(mothership_bus(env, bus_name, route, run_duration))


def bus_scheduler(env):
    # Initially 4 buses that run all day
    launch_buses(2, "OffPeak-AM", SIM_TIME + 60, "red")
    launch_buses(1, "OffPeak-AM", SIM_TIME + 60, "blue")
    yield env.timeout(60)  # 06:00 → 07:00

    # # Peak hours - launch two more
    launch_buses(2, "OffPeak-AM", 240, "red")
    launch_buses(1, "OffPeak-AM", 240, "blue")
    yield env.timeout(540)  # 07:00–16:00

    # # Evening peak (12 buses)
    launch_buses(2, "OffPeak-AM", 180, "red")
    launch_buses(1, "OffPeak-AM", 180, "blue")
    yield env.timeout(180)  # 16:00–19:00


# === Analysis Functions ===
def analyze_bus_utilization():
    """Analyze bus utilization patterns"""
    if not bus_states:
        return {}

    all_states = []
    for bus_id, states in bus_states.items():
        all_states.extend(states)

    if not all_states:
        return {}

    total_observations = len(all_states)
    empty_count = sum(1 for state in all_states if state['passengers'] == 0)
    full_count = sum(1 for state in all_states if state['passengers'] == state['capacity'])

    utilizations = [state['utilization'] for state in all_states]
    avg_utilization = sum(utilizations) / len(utilizations) if utilizations else 0

    return {
        'total_observations': total_observations,
        'percent_empty': (empty_count / total_observations) * 100,
        'percent_full': (full_count / total_observations) * 100,
        'average_utilization': avg_utilization * 100,
        'can_board_probability': ((total_observations - full_count) / total_observations) * 100
    }


def print_comprehensive_report():
    """Print detailed simulation results"""
    print("="*80)
    print("COMPREHENSIVE TRANSPORT SIMULATION RESULTS")
    print("="*80)

    # Passenger Transport Analysis
    print("\n--- PASSENGER TRANSPORT ---")
    print(f"Total passengers created:     {len(all_passengers)}")
    print(f"Total passengers served:      {len(served_passengers)}")
    print(f"Total passengers missed:      {len(all_passengers) - len(served_passengers)}")
    print(f"Service rate:                 {len(served_passengers)/len(all_passengers)*100:.1f}%")

    if served_passengers:
        wait_times = [p['wait_time'] for p in served_passengers if 'wait_time' in p]
        if wait_times:
            print(f"Average wait time:            {sum(wait_times)/len(wait_times):.2f} minutes")

    # Bus Utilization Analysis
    print("\n--- BUS UTILIZATION ---")
    util_stats = analyze_bus_utilization()
    if util_stats:
        print(f"Average bus utilization:      {util_stats['average_utilization']:.1f}%")
        print(f"Time buses empty:             {util_stats['percent_empty']:.1f}%")
        print(f"Time buses full:              {util_stats['percent_full']:.1f}%")
        print(f"Probability passenger can board: {util_stats['can_board_probability']:.1f}%")

    # # Package Delivery Analysis
    # print("\n--- PACKAGE DELIVERY ---")
    # print(f"Total packages created:       {len(all_packages)}")
    # print(f"Total packages delivered:     {len(delivered_packages)}")
    # print(f"Total packages missed:        {len(missed_packages)}")
    # if all_packages:
    #     print(f"Delivery rate:                {len(delivered_packages)/len(all_packages)*100:.1f}%")
    #
    # if delivered_packages:
    #     delivery_times = [p['total_time'] for p in delivered_packages if 'total_time' in p]
    #     if delivery_times:
    #         print(f"Average delivery time:        {sum(delivery_times)/len(delivery_times):.2f} minutes")
    #
    # # Per-Neighborhood Analysis
    # print("\n--- PER-NEIGHBORHOOD PASSENGER ANALYSIS ---")
    # print(f"{'Neighborhood':<25} | {'Created':<8} | {'Served':<8} | {'Missed':<8} | {'Avg Wait':<10}")
    # print("-" * 75)
    #
    # for stop in NEIGHBORHOODS:
    #     created = len([p for p in all_passengers if p['origin'] == stop])
    #     served = len([p for p in served_passengers if p['origin'] == stop])
    #     missed = len([p for p in missed_passengers if p['origin'] == stop])
    #
    #     wait_times = [p['wait_time'] for p in served_passengers
    #                   if p['origin'] == stop and 'wait_time' in p]
    #     avg_wait = sum(wait_times) / len(wait_times) if wait_times else 0
    #
    #     print(f"{stop:<25} | {created:<8} | {served:<8} | {missed:<8} | {avg_wait:<10.2f}")
    #
    # print("\n--- PER-NEIGHBORHOOD PACKAGE ANALYSIS ---")
    # print(f"{'Neighborhood':<25} | {'Created':<8} | {'Delivered':<10} | {'Missed':<8}")
    # print("-" * 60)
    #
    # for stop in NEIGHBORHOODS:
    #     created = len([p for p in all_packages if p['origin'] == stop])
    #     delivered = len([p for p in delivered_packages if p['origin'] == stop])
    #     missed = len([p for p in missed_packages if p['origin'] == stop])
    #
    #     print(f"{stop:<25} | {created:<8} | {delivered:<10} | {missed:<8}")


# === Simulation Setup ===
env = simpy.Environment()

# Start passenger generators
for stop in BLUE_BUS_STOPS:
    env.process(generate_passengers(env, stop, BLUE_ROUTE))
for stop in RED_BUS_STOPS:
    env.process(generate_passengers(env, stop, RED_ROUTE, "forward"))
    env.process(generate_passengers(env, stop, RED_ROUTE, "backward"))


# Start schedulers
env.process(bus_scheduler(env))
# env.process(robot_scheduler(env))

# Run simulation
env.run(until=SIM_TIME + 60) # One extra hour for buses to drop off the remaining passengers

# === Post-processing ===
# Add missed passengers and packages
# for queue in package_queues.values():
#     missed_packages.extend(queue)

# Run the comprehensive analysis
print_comprehensive_report()
