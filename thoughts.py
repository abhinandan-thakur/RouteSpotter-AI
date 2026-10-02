# we need to creat an api first

# input {
#     start: location
#     end : location
# }

# or 
# imput {
#     start: latitude, longitude
#     end: latitude, longitude
# }

# or rather a mapping for interchangeability because i don't think every lat,long has a city name or location name in us
# well idk i am not from us
# TODO maybe i should end constrain in the input api too

# now for output
# fast, low latncy
# output {
#     #  total mony spnt on ful: xxx
#     # rtunr a map of thr rout
#     # basically rturn all th stations neeeded
#     # thn map thm latr
# }


# will a* work bttr than jiktras?

# TODO i need to write tests too

# * OUTPUT
# {
#   "route": {
#     "distance_miles": 790.4,
#     "duration_minutes": 720,
#     "geometry": "..."
#   },
#   "fuel": {
#     "mpg": 10,
#     "total_gallons": 79.04,
#     "total_cost": 245.32
#   },
#   "fuel_stops": [
#     {
#       "name": "Station A",
#       "latitude": 40.1,
#       "longitude": -75.2,
#       "price_per_gallon": 3.12,
#       "distance_from_start": 285.4
#     }
#   ]
# }


# ! I havent' reviewed services.py and tests.py and import_fuel_stops.py lets rememebrt htat 
# ! it is important