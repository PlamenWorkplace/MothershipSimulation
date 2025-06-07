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

BUS_PASSENGER_CAPACITY = 22  # Updated from demand estimation
BUS_ROBOT_CAPACITY = 12
ROBOTS_IN_WAREHOUSE = 72
SIM_TIME = 960  # minutes (6:00 to 22:00)
STOP_TIME = 0.5
TRIP_INTERVAL = 5  # Reduced from 15 to increase frequency
ROBOT_CAPACITY = 10  # packages per robot
ROBOT_SPEED = 5  # minutes per delivery


# === Global tracking variables ===
stop_queues_red_route_forward = {stop["stop"]: deque() for stop in RED_ROUTE}
stop_queues_red_route_backward = {stop["stop"]: deque() for stop in RED_ROUTE}
stop_queues_blue_route = {stop["stop"]: deque() for stop in BLUE_ROUTE}
robot_queues_red_route_backward = {stop["stop"]: deque() for stop in RED_ROUTE}
robot_queues_blue_route = {stop["stop"]: deque() for stop in BLUE_ROUTE}
all_passengers = []
served_passengers = []
all_packages = []
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
    if time >= SIM_TIME:
        return 0

    # Find the stop dict in the route that matches stop_name
    stop_info = next((stop for stop in route if stop["stop"] == stop_name), None)
    if stop_info is None:
        raise ValueError(f"Stop {stop_name} not found in route")

    base_daily_demand = stop_info.get("expected_daily_passengers", 0)
    return base_daily_demand * minute_weights[int(time)]


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

        if arrival_time > SIM_TIME - 60:
            break

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


def get_robots(env, route, direction):
    global ROBOTS_IN_WAREHOUSE

    if route == RED_ROUTE and direction == "backward":
        return []

    route_colour = "red" if route is RED_ROUTE else "blue"
    result = []

    with package_lock.request() as req:
        yield req

        for pkg in all_packages:
            if (
                    pkg["status"] == "waiting_in_warehouse"
                    and pkg["route_colour"] == route_colour
                    and pkg["arrival_time"] <= env.now
            ):
                if ROBOTS_IN_WAREHOUSE <= 0:
                    break

                pkg["status"] = "onboard"
                result.append(pkg)
                ROBOTS_IN_WAREHOUSE -= 1

                if len(result) >= BUS_ROBOT_CAPACITY:
                    break

    return result


def generate_packages(env):
    all_stops = list({stop["stop"] for stop in RED_ROUTE + BLUE_ROUTE})

    while True:
        arrival_time = env.now

        if arrival_time > SIM_TIME - 180:
            break

        delivery_stop = random.choice(all_stops)
        # Determine which route the delivery stop is on
        if any(stop["stop"] == delivery_stop for stop in RED_ROUTE):
            route_colour = "red"
        else:
            route_colour = "blue"

        package = {
            "delivery_stop": delivery_stop,
            "route_colour": route_colour,
            "arrival_time": arrival_time,
            "delivery_time": None,
            "status": "waiting_in_warehouse",
            "onboard_bus_id": None
        }

        all_packages.append(package)

        yield env.timeout(random.expovariate(0.25))


def mothership_bus(env, bus_id, route, run_duration):
    """Enhanced bus process with realistic travel times and utilization tracking"""
    global ROBOTS_IN_WAREHOUSE
    onboard_passengers = []
    end_time = env.now + run_duration

    last_trip = False
    all_stops = [stop["stop"] for stop in route]
    stops = [stop["stop"] for stop in route]
    direction = "forward"
    try:
        while True:
            stop_queues = get_stop_queues(route, direction)
            onboard_robots = yield from get_robots(env, route, direction)
            for i, current_stop in enumerate(stops):
                if env.now >= end_time:
                    last_trip = True

                # Drop-off passengers
                initial_onboard = len(onboard_passengers)
                drop_offs = [p for p in onboard_passengers if p['destination'] == current_stop]
                drop_offs_robots = [p for p in onboard_robots if p['delivery_stop'] == current_stop]
                for passenger in drop_offs:
                    onboard_passengers.remove(passenger)
                    passenger['dropoff_time'] = env.now
                    passenger['travel_time'] = passenger['dropoff_time'] - passenger['pickup_time']
                    served_passengers.append(passenger)
                if not last_trip:
                    for robot in drop_offs_robots:
                        onboard_robots.remove(robot)
                        env.process(deliver_package(env, robot, route, current_stop))

                # Stop time
                if current_stop == "Broekakkerseweg 26" or current_stop == "Eindhoven, Wijnpeerstraat":
                    if last_trip and "Broekakkerseweg 26":
                        return
                    yield env.timeout(random.expovariate(TRIP_INTERVAL))  # TRIP_INTERVAL between 5 and 10
                else:
                    yield env.timeout(random.expovariate(STOP_TIME))  # STOP_TIME between 0.5 and 1

                # Pick-up passengers
                picked_up = 0

                if not last_trip:
                    queue = stop_queues[current_stop]
                    while queue and len(onboard_passengers) < BUS_PASSENGER_CAPACITY:
                        passenger = queue.popleft()
                        passenger['pickup_time'] = env.now
                        passenger['wait_time'] = passenger['pickup_time'] - passenger['arrival_time']
                        onboard_passengers.append(passenger)
                        picked_up += 1

                    # Pick up robots
                    if route != RED_ROUTE or direction == "backward":
                        if route == BLUE_ROUTE:
                            queue = robot_queues_blue_route[current_stop]
                        else:
                            queue = robot_queues_red_route_backward[current_stop]

                        while queue and len(onboard_robots) < BUS_ROBOT_CAPACITY:
                            robot = queue.popleft()
                            robot['pickup_time'] = env.now
                            onboard_robots.append(robot)


                # Record bus state
                bus_states[bus_id].append({
                    'time': env.now,
                    'stop': current_stop,
                    'passengers': len(onboard_passengers),
                    'capacity': BUS_PASSENGER_CAPACITY,
                    'utilization': len(onboard_passengers) / BUS_PASSENGER_CAPACITY,
                    'picked_up': picked_up,
                    'dropped_off': initial_onboard - len(onboard_passengers) + len(drop_offs),
                    'robots': len(onboard_robots)
                })

                # Travel to next stop (if not last stop)
                travel_time = route[i]['travel_time_to_next']
                yield env.timeout(travel_time)

            # Return robots to warehouse
            if route != RED_ROUTE or direction == "backward":
                with package_lock.request() as req:
                    yield req
                    ROBOTS_IN_WAREHOUSE = ROBOTS_IN_WAREHOUSE + len(onboard_robots)

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


def deliver_package(env, robot, route, stop_name):
    yield env.timeout(random.expovariate(ROBOT_SPEED)) # Time to delivery
    robot['delivery_time'] = env.now
    robot['status'] = "delivered"
    yield env.timeout(random.expovariate(ROBOT_SPEED)) # Time to return to bus station
    if route == RED_ROUTE:
        robot_queues_red_route_backward[stop_name].append(robot)
    elif route == BLUE_ROUTE:
        robot_queues_blue_route[stop_name].append(robot)


def launch_buses(num, label_prefix, run_duration, route_colour):
    for i in range(num):
        bus_name = f"{label_prefix}-{i+1}"
        route = RED_ROUTE if route_colour == "red" else BLUE_ROUTE
        env.process(mothership_bus(env, bus_name, route, run_duration))


def mothership_scheduler(env):
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

    # Package Delivery Analysis
    print("\n--- PACKAGE DELIVERY ---")
    delivered_packages = [p for p in all_packages if p["status"] == "delivered"]
    print(f"Total packages delivered:     {len(delivered_packages)}")
    still_in_warehouse = [p for p in all_packages if p["status"] == "waiting_in_warehouse"]
    print(f"Packages still in warehouse:  {len(still_in_warehouse)}")

    if delivered_packages:
        delivery_times = [p['total_time'] for p in delivered_packages if 'total_time' in p]
        if delivery_times:
            print(f"Average delivery time:        {sum(delivery_times)/len(delivery_times):.2f} minutes")

    # Per-Neighborhood Analysis
    print("\n--- PER-NEIGHBORHOOD PASSENGER ANALYSIS ---")
    print(f"{'Neighborhood':<31} | {'Created':<8} | {'Served':<8} | {'Avg Wait':<10}")
    print("-" * 75)

    ALL_UNIQUE_BUS_STOPS = set([stop["stop"] for stop in BLUE_ROUTE] + [stop["stop"] for stop in RED_ROUTE])
    for stop in ALL_UNIQUE_BUS_STOPS:
        created = len([p for p in all_passengers if p['origin'] == stop])
        served = len([p for p in served_passengers if p['origin'] == stop])

        wait_times = [p['wait_time'] for p in served_passengers
                      if p['origin'] == stop and 'wait_time' in p]
        avg_wait = sum(wait_times) / len(wait_times) if wait_times else 0

        print(f"{stop:<31} | {created:<8} | {served:<8} | {avg_wait:<10.2f}")

    print("\n--- PER-NEIGHBORHOOD PACKAGE ANALYSIS ---")
    print(f"{'Neighborhood':<31} | {'Created':<8} | {'Delivered':<10} | {'Missed':<8}")
    print("-" * 60)

    for stop in ALL_UNIQUE_BUS_STOPS:
        created = len([p for p in all_packages if p['delivery_stop'] == stop and p['delivery_stop'] != "Broekakkerseweg 26"])
        delivered = len([p for p in delivered_packages if p['delivery_stop'] == stop and p['delivery_stop'] != "Broekakkerseweg 26"])
        missed = len([p for p in missed_packages if p['delivery_stop'] == stop and p['delivery_stop'] != "Broekakkerseweg 26"])

        print(f"{stop:<31} | {created:<8} | {delivered:<10} | {missed:<8}")


# === Simulation Setup ===
env = simpy.Environment()
package_lock = simpy.Resource(env, capacity=1)


# Start passenger generators
for stop in BLUE_BUS_STOPS:
    env.process(generate_passengers(env, stop, BLUE_ROUTE))
for stop in RED_BUS_STOPS:
    env.process(generate_passengers(env, stop, RED_ROUTE, "forward"))
    env.process(generate_passengers(env, stop, RED_ROUTE, "backward"))

env.process(generate_packages(env))

# Start schedulers
env.process(mothership_scheduler(env))

# Run simulation
env.run(until=SIM_TIME + 60) # One extra hour for buses to drop off the remaining passengers

# === Post-processing ===
# Add missed passengers and packages
package_queues = {**robot_queues_red_route_backward, **robot_queues_blue_route}
for queue in package_queues.values():
    missed_packages.extend(queue)

# Run the comprehensive analysis
print_comprehensive_report()
