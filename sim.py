import simpy
import random
import numpy as np
from collections import deque, defaultdict
import math

# === Parameters ===
NEIGHBORHOODS = [
    "Tongelre", "T'Hofke", "Woensel", "Stratum", "Genderbeemd/Hanevoet",
    "Strijp-S", "Blixembosch-Oost", "Vaartbroek/Eckart", "City Centre",
    "Rozenknopje", "Oud-Woensel"
]

# Target daily demand: 817 passengers (20% of 4083 expected from CSV)
DAILY_TARGET_PASSENGERS = 817

# Neighborhood data from demand estimation - using proportional distribution of 817 target
NEIGHBORHOOD_DATA = {
    "Tongelre": {"inhabitants": 6470, "transport_usage": 0.04, "expected_passengers": 51},   # 259/4152 * 817
    "T'Hofke": {"inhabitants": 3966, "transport_usage": 0.03, "expected_passengers": 23},    # 119/4152 * 817
    "Woensel": {"inhabitants": 6608, "transport_usage": 0.06, "expected_passengers": 78},    # 396/4152 * 817
    "Stratum": {"inhabitants": 8315, "transport_usage": 0.05, "expected_passengers": 82},    # 416/4152 * 817
    "Genderbeemd/Hanevoet": {"inhabitants": 5356, "transport_usage": 0.03, "expected_passengers": 32}, # 161/4152 * 817
    "Strijp-S": {"inhabitants": 3125, "transport_usage": 0.09, "expected_passengers": 55},   # 281/4152 * 817
    "Blixembosch-Oost": {"inhabitants": 7386, "transport_usage": 0.03, "expected_passengers": 44}, # 222/4152 * 817
    "Vaartbroek/Eckart": {"inhabitants": 5356, "transport_usage": 0.06, "expected_passengers": 63}, # 321/4152 * 817
    "City Centre": {"inhabitants": 10230, "transport_usage": 0.08, "expected_passengers": 161}, # 818/4152 * 817
    "Rozenknopje": {"inhabitants": 6985, "transport_usage": 0.06, "expected_passengers": 83},  # 419/4152 * 817
    "Oud-Woensel": {"inhabitants": 12335, "transport_usage": 0.06, "expected_passengers": 145}  # 740/4152 * 817
}

# Travel time matrix (minutes) - realistic distances between neighborhoods
TRAVEL_TIMES = {
    "Tongelre": {"Tongelre": 0, "T'Hofke": 8, "Woensel": 12, "Stratum": 6, "Genderbeemd/Hanevoet": 10, 
                 "Strijp-S": 15, "Blixembosch-Oost": 7, "Vaartbroek/Eckart": 9, "City Centre": 11, 
                 "Rozenknopje": 14, "Oud-Woensel": 16},
    "T'Hofke": {"Tongelre": 8, "T'Hofke": 0, "Woensel": 6, "Stratum": 10, "Genderbeemd/Hanevoet": 5, 
                "Strijp-S": 12, "Blixembosch-Oost": 9, "Vaartbroek/Eckart": 7, "City Centre": 8, 
                "Rozenknopje": 11, "Oud-Woensel": 13},
    "Woensel": {"Tongelre": 12, "T'Hofke": 6, "Woensel": 0, "Stratum": 14, "Genderbeemd/Hanevoet": 8, 
                "Strijp-S": 9, "Blixembosch-Oost": 15, "Vaartbroek/Eckart": 4, "City Centre": 5, 
                "Rozenknopje": 7, "Oud-Woensel": 3},
    "Stratum": {"Tongelre": 6, "T'Hofke": 10, "Woensel": 14, "Stratum": 0, "Genderbeemd/Hanevoet": 12, 
                "Strijp-S": 18, "Blixembosch-Oost": 4, "Vaartbroek/Eckart": 13, "City Centre": 8, 
                "Rozenknopje": 16, "Oud-Woensel": 17},
    "Genderbeemd/Hanevoet": {"Tongelre": 10, "T'Hofke": 5, "Woensel": 8, "Stratum": 12, "Genderbeemd/Hanevoet": 0, 
                             "Strijp-S": 11, "Blixembosch-Oost": 13, "Vaartbroek/Eckart": 6, "City Centre": 7, 
                             "Rozenknopje": 9, "Oud-Woensel": 10},
    "Strijp-S": {"Tongelre": 15, "T'Hofke": 12, "Woensel": 9, "Stratum": 18, "Genderbeemd/Hanevoet": 11, 
                 "Strijp-S": 0, "Blixembosch-Oost": 20, "Vaartbroek/Eckart": 8, "City Centre": 6, 
                 "Rozenknopje": 4, "Oud-Woensel": 7},
    "Blixembosch-Oost": {"Tongelre": 7, "T'Hofke": 9, "Woensel": 15, "Stratum": 4, "Genderbeemd/Hanevoet": 13, 
                         "Strijp-S": 20, "Blixembosch-Oost": 0, "Vaartbroek/Eckart": 16, "City Centre": 12, 
                         "Rozenknopje": 18, "Oud-Woensel": 19},
    "Vaartbroek/Eckart": {"Tongelre": 9, "T'Hofke": 7, "Woensel": 4, "Stratum": 13, "Genderbeemd/Hanevoet": 6, 
                          "Strijp-S": 8, "Blixembosch-Oost": 16, "Vaartbroek/Eckart": 0, "City Centre": 3, 
                          "Rozenknopje": 5, "Oud-Woensel": 2},
    "City Centre": {"Tongelre": 11, "T'Hofke": 8, "Woensel": 5, "Stratum": 8, "Genderbeemd/Hanevoet": 7, 
                    "Strijp-S": 6, "Blixembosch-Oost": 12, "Vaartbroek/Eckart": 3, "City Centre": 0, 
                    "Rozenknopje": 4, "Oud-Woensel": 6},
    "Rozenknopje": {"Tongelre": 14, "T'Hofke": 11, "Woensel": 7, "Stratum": 16, "Genderbeemd/Hanevoet": 9, 
                    "Strijp-S": 4, "Blixembosch-Oost": 18, "Vaartbroek/Eckart": 5, "City Centre": 4, 
                    "Rozenknopje": 0, "Oud-Woensel": 8},
    "Oud-Woensel": {"Tongelre": 16, "T'Hofke": 13, "Woensel": 3, "Stratum": 17, "Genderbeemd/Hanevoet": 10, 
                    "Strijp-S": 7, "Blixembosch-Oost": 19, "Vaartbroek/Eckart": 2, "City Centre": 6, 
                    "Rozenknopje": 8, "Oud-Woensel": 0}
}

BUS_CAPACITY = 22  # Updated from demand estimation
STOP_TIME = 1
TRIP_INTERVAL = 5  # Reduced from 15 to increase frequency
SIM_TIME = 960  # minutes (6:00 to 22:00)

# Package delivery parameters
DAILY_PACKAGES = 248  # From demand estimation
ROBOT_CAPACITY = 10  # packages per robot
ROBOT_SPEED = 3  # minutes per delivery
PICKUP_WAIT_TIME = (5, 15)  # min, max wait time for robot pickup

PEAK_HOURS = [(60, 180), (600, 720)]  # 07:00–10:00 and 16:00–19:00

# === Global tracking variables ===
stop_queues = {stop: deque() for stop in NEIGHBORHOODS}
package_queues = {stop: deque() for stop in NEIGHBORHOODS}
all_passengers = []
served_passengers = []
missed_passengers = []
all_packages = []
delivered_packages = []
missed_packages = []

# Bus utilization tracking
bus_utilization_data = []
bus_states = defaultdict(list)  # Track empty/full states

def get_passenger_rate(time, neighborhood):
    """Get passenger arrival rate based on time and neighborhood characteristics"""
    # Total expected passengers for this neighborhood for the entire day
    daily_passengers = NEIGHBORHOOD_DATA[neighborhood]["expected_passengers"]
    
    # Distribute across the 16-hour service period (960 minutes)
    # Peak hours get 60% of daily demand, off-peak gets 40%
    peak_minutes = 240  # 4 hours of peak time (07:00-09:00, 16:00-19:00)
    offpeak_minutes = 720  # 12 hours of off-peak time
    
    if 60 <= time < 180 or 600 <= time < 720:  # Peak hours
        # 60% of daily passengers distributed over 240 peak minutes
        return (daily_passengers * 0.6) / peak_minutes
    else:  # Off-peak hours
        # 40% of daily passengers distributed over 720 off-peak minutes
        return (daily_passengers * 0.4) / offpeak_minutes

def get_package_rate(neighborhood):
    """Get package generation rate based on neighborhood population"""
    inhabitants = NEIGHBORHOOD_DATA[neighborhood]["inhabitants"]
    total_inhabitants = sum(data["inhabitants"] for data in NEIGHBORHOOD_DATA.values())
    neighborhood_share = inhabitants / total_inhabitants
    return (DAILY_PACKAGES * neighborhood_share) / SIM_TIME

def generate_passengers(env, stop_name):
    """Generate passengers with realistic demand patterns"""
    while True:
        current_rate = get_passenger_rate(env.now, stop_name)
        if current_rate > 0:
            # Convert rate per minute to exponential distribution parameter
            yield env.timeout(random.expovariate(current_rate))
        else:
            yield env.timeout(5)  # Check every 5 minutes if rate is 0
            continue
            
        # Weighted destination selection based on travel times and attractiveness
        destinations = [s for s in NEIGHBORHOODS if s != stop_name]
        weights = []
        for dest in destinations:
            # Shorter travel time = higher probability, City Centre is more attractive
            travel_time = TRAVEL_TIMES[stop_name][dest]
            weight = 1 / (travel_time ** 0.5)  # Inverse relationship with travel time
            if dest == "City Centre":
                weight *= 2  # City Centre is twice as attractive
            weights.append(weight)
        
        destination = random.choices(destinations, weights=weights)[0]
        
        passenger = {
            "origin": stop_name,
            "destination": destination,
            "arrival_time": env.now,
            "id": len(all_passengers)
        }
        stop_queues[stop_name].append(passenger)
        all_passengers.append(passenger)

def generate_packages(env, stop_name):
    """Generate packages for delivery"""
    package_rate = get_package_rate(stop_name)
    
    while True:
        if package_rate > 0:
            yield env.timeout(random.expovariate(package_rate))
        else:
            yield env.timeout(10)  # Check every 10 minutes
            continue
            
        # Random destination weighted by population
        destinations = [s for s in NEIGHBORHOODS if s != stop_name]
        weights = [NEIGHBORHOOD_DATA[dest]["inhabitants"] for dest in destinations]
        destination = random.choices(destinations, weights=weights)[0]
        
        package = {
            "origin": stop_name,
            "destination": destination,
            "creation_time": env.now,
            "id": len(all_packages)
        }
        package_queues[stop_name].append(package)
        all_packages.append(package)

def mothership_bus(env, bus_id, route_order):
    """Enhanced bus process with realistic travel times and utilization tracking"""
    onboard_passengers = []
    
    while True:
        route_start_time = env.now
        
        for i, current_stop in enumerate(route_order):
            arrival_time = env.now
            
            # Drop-off passengers
            initial_onboard = len(onboard_passengers)
            drop_offs = [p for p in onboard_passengers if p['destination'] == current_stop]
            for passenger in drop_offs:
                onboard_passengers.remove(passenger)
                passenger['dropoff_time'] = env.now
                passenger['travel_time'] = passenger['dropoff_time'] - passenger['pickup_time']
            
            # Pick-up passengers
            queue = stop_queues[current_stop]
            picked_up = 0
            while queue and len(onboard_passengers) < BUS_CAPACITY:
                passenger = queue.popleft()
                passenger['pickup_time'] = env.now
                passenger['wait_time'] = passenger['pickup_time'] - passenger['arrival_time']
                served_passengers.append(passenger)
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
            
            # Stop time
            yield env.timeout(STOP_TIME)
            
            # Travel to next stop (if not last stop)
            if i < len(route_order) - 1:
                next_stop = route_order[i + 1]
                travel_time = TRAVEL_TIMES[current_stop][next_stop]
                yield env.timeout(travel_time)
        
        # Wait before starting next trip
        yield env.timeout(TRIP_INTERVAL)

def delivery_robot(env, robot_id, origin_stop):
    """Robot delivery process with pickup by mothership"""
    packages_carried = []
    
    # Load packages at origin
    queue = package_queues[origin_stop]
    while queue and len(packages_carried) < ROBOT_CAPACITY:
        package = queue.popleft()
        package['pickup_time'] = env.now
        packages_carried.append(package)
    
    if not packages_carried:
        return  # No packages to deliver
    
    # Group packages by destination
    destinations = defaultdict(list)
    for package in packages_carried:
        destinations[package['destination']].append(package)
    
    # Deliver packages
    current_location = origin_stop
    for dest, dest_packages in destinations.items():
        # Travel to destination
        travel_time = TRAVEL_TIMES[current_location][dest]
        yield env.timeout(travel_time)
        current_location = dest
        
        # Deliver packages
        for package in dest_packages:
            yield env.timeout(ROBOT_SPEED)
            package['delivery_time'] = env.now
            package['total_time'] = package['delivery_time'] - package['creation_time']
            delivered_packages.append(package)
    
    # Wait for pickup by mothership
    pickup_wait = random.uniform(*PICKUP_WAIT_TIME)
    yield env.timeout(pickup_wait)

def robot_scheduler(env):
    """Schedule robot deployments based on package demand"""
    robot_counter = 0
    
    while True:
        # Check package queues every 30 minutes
        yield env.timeout(30)
        
        for stop in NEIGHBORHOODS:
            queue_length = len(package_queues[stop])
            if queue_length >= ROBOT_CAPACITY:
                # Deploy robot
                robot_counter += 1
                env.process(delivery_robot(env, f"Robot-{robot_counter}", stop))

def bus_scheduler(env):
    """Dynamic bus scheduling with different routes - more buses for better service"""
    active_buses = []
    
    # Define different route patterns - shorter, more efficient routes
    routes = [
        ["City Centre", "Rozenknopje", "Strijp-S", "Woensel", "Oud-Woensel", "Vaartbroek/Eckart"],  # Central-West route
        ["City Centre", "Vaartbroek/Eckart", "Genderbeemd/Hanevoet", "T'Hofke", "Woensel"],  # Central-North route  
        ["Stratum", "Tongelre", "Blixembosch-Oost", "City Centre"],  # East-Central route
        ["Oud-Woensel", "Woensel", "Rozenknopje", "Strijp-S", "City Centre"],  # West-Central route
        NEIGHBORHOODS,  # Full circle route
        NEIGHBORHOODS[::-1],  # Reverse full circle
    ]
    
    def launch_buses(num, label_prefix):
        for i in range(num):
            bus_name = f"{label_prefix}-{i+1}"
            route = routes[i % len(routes)]  # Rotate through routes
            proc = env.process(mothership_bus(env, bus_name, route))
            active_buses.append(proc)

    # Initially off-peak (8 buses) - increased capacity
    launch_buses(4, "OffPeak")
    yield env.timeout(60)  # 06:00 → 07:00

    # Peak hours (12 buses) - significantly increased
    launch_buses(6, "Peak-AM")
    yield env.timeout(240)  # 07:00–11:00
    
    # Off-peak midday (8 buses)
    yield env.timeout(300)  # 11:00–16:00
    
    # Evening peak (12 buses)
    launch_buses(6, "Peak-PM")
    yield env.timeout(180)  # 16:00–19:00

# === Simulation Setup ===
env = simpy.Environment()

# Start passenger generators
for stop in NEIGHBORHOODS:
    env.process(generate_passengers(env, stop))
    env.process(generate_packages(env, stop))

# Start schedulers
env.process(bus_scheduler(env))
env.process(robot_scheduler(env))

# Run simulation
env.run(until=SIM_TIME)

# === Post-processing ===
# Add missed passengers and packages
for queue in stop_queues.values():
    missed_passengers.extend(queue)

for queue in package_queues.values():
    missed_packages.extend(queue)

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
    
    # Expected vs Actual Demand Comparison
    print("\n--- DEMAND VALIDATION ---")
    total_expected = sum(data["expected_passengers"] for data in NEIGHBORHOOD_DATA.values())
    print(f"Expected daily passengers:    {total_expected}")
    print(f"Actual passengers created:    {len(all_passengers)}")
    print(f"Demand accuracy:              {len(all_passengers)/total_expected*100:.1f}%")
    
    # Passenger Transport Analysis
    print("\n--- PASSENGER TRANSPORT ---")
    print(f"Total passengers created:     {len(all_passengers)}")
    print(f"Total passengers served:      {len(served_passengers)}")
    print(f"Total passengers missed:      {len(missed_passengers)}")
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
    print(f"Total packages created:       {len(all_packages)}")
    print(f"Total packages delivered:     {len(delivered_packages)}")
    print(f"Total packages missed:        {len(missed_packages)}")
    if all_packages:
        print(f"Delivery rate:                {len(delivered_packages)/len(all_packages)*100:.1f}%")
    
    if delivered_packages:
        delivery_times = [p['total_time'] for p in delivered_packages if 'total_time' in p]
        if delivery_times:
            print(f"Average delivery time:        {sum(delivery_times)/len(delivery_times):.2f} minutes")
    
    # Per-Neighborhood Analysis
    print("\n--- PER-NEIGHBORHOOD PASSENGER ANALYSIS ---")
    print(f"{'Neighborhood':<25} | {'Created':<8} | {'Served':<8} | {'Missed':<8} | {'Avg Wait':<10}")
    print("-" * 75)
    
    for stop in NEIGHBORHOODS:
        created = len([p for p in all_passengers if p['origin'] == stop])
        served = len([p for p in served_passengers if p['origin'] == stop])
        missed = len([p for p in missed_passengers if p['origin'] == stop])
        
        wait_times = [p['wait_time'] for p in served_passengers 
                     if p['origin'] == stop and 'wait_time' in p]
        avg_wait = sum(wait_times) / len(wait_times) if wait_times else 0
        
        print(f"{stop:<25} | {created:<8} | {served:<8} | {missed:<8} | {avg_wait:<10.2f}")
    
    print("\n--- PER-NEIGHBORHOOD PACKAGE ANALYSIS ---")
    print(f"{'Neighborhood':<25} | {'Created':<8} | {'Delivered':<10} | {'Missed':<8}")
    print("-" * 60)
    
    for stop in NEIGHBORHOODS:
        created = len([p for p in all_packages if p['origin'] == stop])
        delivered = len([p for p in delivered_packages if p['origin'] == stop])
        missed = len([p for p in missed_packages if p['origin'] == stop])
        
        print(f"{stop:<25} | {created:<8} | {delivered:<10} | {missed:<8}")

# Run the comprehensive analysis
print_comprehensive_report()
