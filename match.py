from util import log
from copy import deepcopy
from tinydb import TinyDB, Query

import pprint

db = TinyDB('matchdb.json')

# 2 possible is_buying
buying = [True, False]
# 4 possible dining halls
dining_halls = ["deneve", "bplate", "feast", "covel"]
# 6am - 9pm
times = range(6, 21)
# possible prices are up to $10
prices = range(10)

def init():
	"""
	builds the tree structure for all possible user fields
	"""
	# clear db
	db.purge()

	# buying bottom level
	d = dict((x, []) for x in buying)

	# times bottom level
	d = dict((x, deepcopy(d)) for x in times)

	# adds prices as next top level
	d = dict((x, deepcopy(d)) for x in prices)

	# adds dining halls as top most level
	d = dict((x, deepcopy(d)) for x in dining_halls)
	# insert tree into db
	db.insert(d)

def add_complete_user(usr):
	"""
	adds a user dict in the following format and returns new matches if any
	format of usr:
	{
		halls: list of halls 'BPLATE', 'DENEVE',
		times: list of military times (ints),
		is_buyer: bool,
		id: int representing their uid
	}
	"""
	halls = [hall.lower() for hall in usr["where"]]
	times = usr["when"]
	is_buyer = usr["is_buyer"]
	price = usr["price"]
	uid = usr["id"]
	pp = pprint.PrettyPrinter(indent=4)

	# list of uid pairs containing matches
	# uid1, uid2, hall, time
	matches = []
	d = db.all()[0]
	pp.pprint(d)
	for hall in halls:
		for time in times:
			node = d[hall][str(price)][str(time)][str(is_buyer)]

			if uid not in node:
				d[hall][str(price)][str(time)][str(is_buyer)].append(uid)

			# if seller of the same data but opposite buying status exists
			if d[hall][str(price)][str(time)][str(not is_buyer)]:
				match = d[hall][str(price)][str(time)][str(not is_buyer)]
				matches.append((match[0], uid, hall, time, price))
	pp.pprint(d)
	db.purge()
	db.insert(d)
	return matches

if __name__ == '__main__':
	# example use case
	init()
	usr1 = {'id':1234, 'where':['BPLATE', 'DENEVE'], 'when':[8,9], 'is_buyer':False, 'price':7}
	print add_complete_user(usr1)
	usr2 = {'id':6969, 'where':['BPLATE', 'DENEVE'], 'when':['8','9'], 'is_buyer':'True', 'price':'7'}
	print add_complete_user(usr2)