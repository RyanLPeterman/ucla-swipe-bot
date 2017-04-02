import os
import json

import time
import atexit
import facebook_scraper

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger


import requests
from flask import Flask, request
from collections import defaultdict

from util import log
import messenger_interface as fb
import database as db

app = Flask(__name__)

# The scheduler will only start after the first request. We need to include this
# because the debugger will naturally run two instances and this way we will
# only run one.
@app.before_first_request
def initialize():
    scheduler = BackgroundScheduler()
    scheduler.start()
    scheduler.add_job(
        func=facebook_scraper.test_func,
        trigger=IntervalTrigger(seconds=5),
        id='scraping_job',
        name='Scraping the Facebook page every few hours',
        replace_existing=True)
    atexit.register(lambda: scheduler.shutdown())

# User Data Structure:
# { user_id:
#   { "buyer": bool, - False = seller
#     "when" : list(1, 2, 3) - contains each hour in military time that they are buying
#     "where": list("bplate", "deneve", "covel", "feast") - contains one or more dining halls
#   }
# }

@app.route('/', methods=['GET'])
def verify():
    # when the endpoint is registered as a webhook, it must echo back
    # the 'hub.challenge' value it receives in the query arguments
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.challenge"):
        if not request.args.get("hub.verify_token") == os.environ["VERIFY_TOKEN"]:
            return "Verification token mismatch", 403
        return request.args["hub.challenge"], 200

    return "Hello world", 200

# endpoint for processing incoming messaging events
@app.route('/', methods=['POST'])
def webhook():

    data = request.get_json()
    # for testing
    log(data)

    if data["object"] == "page":
        for entry in data["entry"]:
            for messaging_event in entry["messaging"]:

                # the facebook ID of the person sending you the message
                sender_id = messaging_event["sender"]["id"]
                # the recipient's ID, which should be your page's facebook ID
                recipient_id = messaging_event["recipient"]["id"]

                # someone sent us a message
                if messaging_event.get("message"):
                    # skip message if its an emoji
                    if "text" not in messaging_event["message"]:
                        continue

                    message_text = messaging_event["message"]["text"]  # the message's text

                    # TODO: temporarily starts data request save on begin msg send
                    #       change to on "get started" button press instead later
                    if message_text.lower() == "begin":
                        fb.send_message(sender_id, fb.init_user())
                    else:
                        fb.send_message(sender_id, fb.setup_str("Got a message!"))

                # user clicked/tapped "postback" button in earlier message
                if messaging_event.get("postback"):
                    payload = messaging_event["postback"]["payload"]
                    handle_payload(sender_id, payload)

    return "ok", 200

# handles payload string from postback
# payloads are in the form
#   <action>:<value>
# i.e.
#   set:buyer
#   init:buyer
def handle_payload(uid, payload):
    log("Received postback payload from {id}: {load}".format(id=uid, load=payload))

    action, value = payload.split(":")
    usr = db.get_user_obj(uid)

    if action == "HALL":
        db.add_hall(uid, value)

    elif action == "BUYER":
        db.set_buyer(uid, value == 'buyer')

        # if we have no dining hall data
        if "where" not in usr:
            fb.send_message(uid, fb.init_location())

    # TODO: Convert to NLP to prompt user for time data
    elif action == "TIME":
        db.add_time(uid, int(value))

    # use this postback action to resend prompts
    elif action == "GOTO":
        if value == "TIME":
            fb.send_message(uid, fb.setup_time())
        elif value == "HALL":
            fb.send_message(uid, fb.init_location())
        elif value == "DONE":
            log("USR {uid} State when done: {usr}".format(uid=uid, usr=usr))
            # user gave complete data
            if db.is_user_complete(uid):
                matches = match.add_complete_user(usr)
                log("Added USR {uid} to complete data db".format(uid=uid))

                if not matches:
                    fb.send_message(uid, fb.setup_str("Great! I will try my best to match you and let you know if I find someone!"))
                else:
                    fb.send_message(uid, fb.setup_str(str(matches)))
            else:
                fb.send_message(uid, fb.setup_str("I don't have the complete information necessary to match you, please fill out the following forms"))

                if "where" not in usr:
                    fb.send_message(uid, fb.init_location())
                if "when" not in usr:
                    fb.send_message(uid, fb.setup_time())
                if "is_buyer" not in usr:
                    fb.send_message(uid, fb.init_user())

    else:
        log("Received unhandled payload: {load}".format(load=payload))

if __name__ == '__main__':
    match.init()
    app.run(debug=True)


from copy import deepcopy

# 2 possible is_buying
buying = [True, False]
# 4 possible dining halls
dining_halls = ["DENEVE", "BPLATE", "FEAST", "COVEL"]
# 6am - 9pm
times = range(6, 21)
# possible prices are up to $10
prices = range(10)

def init():
    """
    builds the tree structure for all possible user fields
    """
    # global tree structure
    global d

    # buying bottom level
    d = dict((x, []) for x in buying)

    # times bottom level
    d = dict((x, deepcopy(d)) for x in times)

    # adds prices as next top level
    # d = dict((x, d) for x in prices)

    # adds dining halls as top most level
    d = dict((x, deepcopy(d)) for x in dining_halls)

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
    halls = usr["where"]
    times = usr["when"]
    is_buyer = usr["is_buyer"]
    uid = usr["id"]

    # list of uid pairs containing matches
    # uid1, uid2, hall, time
    matches = []

    for hall in halls:
        for time in times:
            node = d[hall][time][is_buyer]

            if uid not in node:
                d[hall][time][is_buyer].append(uid)

            # if seller of the same data but opposite buying status exists
            if d[hall][time][not is_buyer]:
                match = d[hall][time][not is_buyer]
                matches.append((match[0], uid, hall, time))

    return matches