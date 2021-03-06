# coding=utf-8

import logging, os, time, subprocess, re, sys, time, random, string
from datetime import *
from telegram import *
from telegram.ext import *
sys.path.append("python_mvg_api")
from mvg_api import *
import key, plans

plans = plans.plans
updater = Updater(key.key) #api key from file "key.py", create your's as shown in "key_sample.py"
timer = updater.job_queue
refresh = ([])
station_ids = {}

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

weekdays = ["Mo","Di","Mi","Do","Fr","Sa","So"]

shortcuts = {
    u"lab": {"gps":(48.158681, 11.550225), "name": "MunichMakerLab"},
    u"mgm": {"gps":(48.119908, 11.638493), "name": "MichaeliGymnasium"},
    u"💩": {"gps":(48.177038, 11.591554), "name": u"""CSU - "Christlich" Soziale* Union 💩"""},
    u"marat": {"gps":(48.1239256, 11.5603815), "name": "Kafe Marat"}
}
walkEmojis = [u"🚶",u"🏃",u"💃",u"🐢"]

emojiList = [u"🌈", u"🤓", u"👹", u"👽", u"👌", u"🖕", u"👅", u"👁", u"👩", u"‍💻", u"👨", u"🎨", u"🎅", u"💆", u"🐣", u"🕷", u"🐉", u"☃", u"🏏"]

allowed_chars = string.ascii_letters + " :-ßüöäÜÄÖ.@i0123456789" + "".join(emojiList)

def start(bot, update):
    bot.sendMessage(update.message.chat_id, text='Hallo, sende mir den Name einer Haltestelle oder teile deinen Standort, um die Abfahrten für eine Haltestelle zu sehen.\nBenutze /help um mehr Informationen zu erhalten (z.B. über die Routenplanung)')
    logger.info('start used by %s', update.message.from_user)

def help(bot, update):
    #bot.sendMessage(update.message.chat_id, text='This bot will send you the departure times of public transport stations in Munich (Germany).')
    bot.sendMessage(update.message.chat_id, text='sende mir den Name einer Haltestelle oder teile deinen Standort, um die Abfahrten für eine Haltestelle zu sehen.\n\nRouten können z.B. so geplant werden:\nMarienpaltz nach Obersendling um 20:00\noder\nOdensplatz nach Siemenswerke bis 21:00\noder\nTrudering nach Kreillerstraße\n\nFormel:\nfromStation [nach|to] toStation ([ab|um|bis|at|until] hh:mm)')
    logger.info('help used by %s', update.message.from_user)

def gps(bot, update):
    lat = update.message.location.latitude
    lon = update.message.location.longitude
    stations = get_nearby_stations(lat, lon)
    if stations == []:
        bot.sendMessage(update.message.chat_id, text='Keine Stationen in der Nähe gefunden')
        logger.info('No station found near %s', update.message.from_user)
    else:
        buttons = []
        buttons.append([])
        buttons[0].append(InlineKeyboardButton(u"📝 Standort speichern", callback_data="gps|split|" + str(lat) + "|" + str(lon)))
        row = 1
        for station in stations:
            buttons.append([])
            service = {'t': "Tram", 'u': "U-Bahn", 'b': "Bus", 's': "S-Bahn"}
            products=""
            count = 0
            for product in station['products']:
                spacing = ""
                if count > 0:
                    spacing = ", "
                try:
                    products = products + spacing + service[product]
                except:
                    products = products+  ", " + product
                count += 1
            products = "(" + products + ")"
            name =  station['name'] + "  " + str(station['distance']) + "m  "+ products
            station_id = station['id']
            split = "station|split|"
            buttons[row].append(InlineKeyboardButton(name, callback_data=split+str(station_id)))
            row += 1
        bot.sendMessage(update.message.chat_id, text="Wähle eine Station:", reply_markup=InlineKeyboardMarkup(buttons))
        logger.info('Sending %s gps station select buttons', update.message.from_user)

def buttonHandler(bot, update):
    update = update.callback_query
    response = update.data.split('|split|')
    dataType = response[0]
    data = response[1]
    if dataType == "station":
        sendDepsforStation(bot, update, data, update.message.message_id)
    elif dataType == "planBack":
        plan(bot, update, edit=True)
    elif dataType == "planCategoryId":
        sendPlanCategory(bot, update, int(data))
    elif dataType == "planPlanId":
        data = data.split('|wurst|')
        sendPlanPlan(bot, update, int(data[1]), int(data[0]))
    elif dataType == "gps":
        data = data.split('|')
        addShortcut(bot, update, float(data[0]), float(data[1]))
    else:
        logger.error("Something went wrong with the buttonHandler, no matching dataType")

def msg(bot, update):
    # bot.sendMessage(chat_id = update.message.chat_id, text = "Die MVG website ist im Moment nicht erreichbar, deshalb kann es zu Verzögerungen bei der Nachrichtenzustellung kommen. 😉")
    logger.debug("New message")
    #thanks to @uberardy for these regular expressions
    pattern1 = "(?:von )?(.+) (nach|to) (.*)"
    pattern2 = "(?:von )?(.+) (nach|to) (.*)(?: (um|ab|bis|at|until) ([0-9]{1,2}:?[0-9]{2}))"
    text = update.message.text
    valid_msg = True
    for char in text:
        if not char in allowed_chars:
            valid_msg = False
            break;
    if valid_msg:
        result1 = re.match(pattern1, text)
        if result1 == None: #not a route
            logger.debug("not a route")
            logger.debug("station")
            sendDepsforStation(bot, update, text)
        else: #route
            logger.debug("route")
            result2 = re.match(pattern2, text)
            if result2 == None:
                result = result1
                b_time = False  # route without time
            else:
                result = result2
                b_time = True  # route with time
            sendRoutes(bot, update, result, b_time)
    else:
        logger.warning("Illegal char {} from {}".format(char, update.message.from_user))
        update.message.reply_text("Nachricht enthällt ein nicht erlaubtes Zeichen")

def getStationDetails(station_raw):
    station = get_stations(station_raw)[0]
    return station['id'],station['name']

def getLocation(raw):
    if "@" in raw[0:3]: # street address
        location = get_locations(raw.strip("@"))[0]
        return (location["latitude"],location["longitude"])
    else:
        return getStationDetails(raw)[0]

def sendLocation(bot, update, gps):
    bot.sendLocation(chat_id=update.message.chat_id, latitude=gps[0], longitude=gps[1])

def sendDepsforStation(bot, update, station_raw, message_id = -1):
    refresh = False
    from_user = update.message.from_user
    if message_id > -1:
        from_user = update.from_user
        refresh = True
    try:
        station_id, station_name = getStationDetails(station_raw)
    except IndexError:
        bot.sendMessage(update.message.chat_id, text="Station nicht gefunden :(")
        logger.warning('Not matching station name in deps used by %s', update.message.from_user)
    else:
        # station_name = "testname" #get_stations(station_id)[0]['name']
        departures = get_departures(station_id)
        if departures == []: #checking if there are deps for the station
            bot.sendMessage(chat_id=update.message.chat_id, text='Keine Abfahrten für diese Station')
            logger.info('No departures for %s, requested by %s', station_raw, from_user)
        else:
            logger.info('deps for %s (%s) to %s. Refresh = %s', station_id, station_name, from_user, refresh)

            now = datetime.datetime.now()
            header="minutes, service, destination"
            body = ""
            times=[]
            products=[]
            destinations=[]
            i=0
            for departure in departures:
                len_dTM = len(str(departure['departureTimeMinutes']))
                if True: # not len_dTM > 3:
                    times.append(str(departure['departureTimeMinutes']))
                    product = build_label(departure['product'], departure['label'])
                    products.append(product)
                    destinations.append(departure['destination'])
                    i=i+1

            maxlen={}
            maxlen['times'] = max(len(s) for s in times)
            maxlen['products'] = max(len(s) for s in products)
            maxlen['destinations'] = max(len(s) for s in destinations)
            if maxlen['destinations'] > 18:
                maxlen['destinations'] = 18

            c = 0
            while(i > 0):
                row=products[c]
                row=addspaces(maxlen['products']-len(products[c])+1, row)
                while len(destinations[c]) > 18:
                    row += destinations[c][:18] + "\n"
                    row = addspaces(maxlen['products']+1, row)
                    destinations[c] = destinations[c][18:]
                row=row+destinations[c]
                row=addspaces(maxlen['destinations']-len(destinations[c])+1,row)
                row=row+times[c]
                body=body+"\n"+row
                i=i-1
                c=c+1

            if body == "":
                body = "\n<i>Keine Abfahrt in den nächsten 999 Minuten</i>"
            else:
                body="<code>" + body + "</code>\n"


            zeit = now.strftime("%H:%M:%S")

            buttons = []
            buttons.append([])
            now = datetime.datetime.now()
            split = "station|split|"
            buttons[0].append(InlineKeyboardButton(zeit + " - tap to refresh", callback_data=split+str(station_id)))
            reply_markup=InlineKeyboardMarkup(buttons)

            station_name = "<b>"+station_name+"</b>"
            station_id_text = "("+str(station_id)+")"

            msg=station_name+" "+station_id_text+" "+body

            if refresh:
                try:
                    bot.editMessageText(chat_id=update.message.chat_id, text=msg, message_id=message_id, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
                except:
                    bot.sendMessage(update.message.chat_id, text="Stop spamming!")
                    logger.warning('User used refresh more than once per second: %s' % (from_user))
            else:
                bot.sendMessage(update.message.chat_id, text=msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

def sendRoutes(bot, update, result, b_time):
    log_time_in_past = False
    start_dest = [] # start and destination of route
    try:
        for sid in [result.group(1),result.group(3)]:
            try:
                start_dest.append(shortcuts[sid.lower()]['gps'])
            except KeyError:
                start_dest.append(getLocation(sid))
    except:

        bot.sendMessage(update.message.chat_id, text="Station nicht gefunden :(")
        logger.warning('Not matching station name in journeys used by %s', update.message.from_user)
    else:
        arrival_time = False
        i_time = datetime_to_mvgtime(datetime.datetime.now())
        if b_time:
            if result.group(4) in ["bis","until"]:
                arrival_time = True
            try:
                dt = datetime.datetime.combine(datetime.datetime.now(), datetime.datetime.strptime(result.group(5), "%H:%M").time())
            except:
                bot.sendMessage(update.message.chat_id, text="Zeit ungültig, bitte im Format hh:mm angeben\nAktuelle Zeit wird jetzt als Alternative verwendet")
                logger.warning('invalid time used by %s', update.message.from_user)
            else:
                if datetime.datetime.now().time() > dt.time():
                    bot.sendMessage(chat_id=update.message.chat_id, text="Liegt in der Vergangneneit!\nEs werden Verbindungen für morgen angezeigt.")
                    dt = dt + datetime.timedelta(days=1)
                    log_time_in_past = True
                i_time = datetime_to_mvgtime(dt)


        route = get_route(start_dest[0], start_dest[1], i_time, arrival_time)
        if route:
            if len(route) > 5:
                if arrival_time:
                    route = route[-5:]
                else:
                    route = route[:5]
            msg = buildRouteMsg(route)

            bot.sendMessage(update.message.chat_id, text=msg, parse_mode=ParseMode.HTML)
            logger.info('journey from {} to {} sent to {}, b_time={}'.format(start_dest[0], start_dest[1], update.message.from_user, b_time))
        else:
            bot.sendMessage(update.message.chat_id, text="Keine Route gefunden :(\nBitte Flugtaxi verwenden.")
            logger.warning('no route between {} and {} for {}'.format(start_dest[0], start_dest[1], update.message.from_user))

def fix_missing(json, tags):
    for tag in tags:
        try:
            x = json[tag]
        except KeyError:
            json[tag] = ""
    return json

def buildRouteMsg(route):
    body=""
    counter=0
    for option in route:
        counter +=1
        if counter > 5:
            logger.info("Limiting number of options!")
            break
        duration = (int(option['arrival']) - int(option['departure'])) // 60000
        fix_missing(option, ["ringFrom","ringTo"])
        body += "\n%s. Option: %s min; Ring %s-%s\n" % (counter, duration, option['ringFrom'], option["ringTo"])
        for part in option['connectionPartList']:
            from_name = name_for_route_part(part['from'])
            to_name = name_for_route_part(part['to'])
            body += mvgtime_to_hrs(part['departure']) + " - " + from_name + "\n"
            if part['connectionPartType'] == "FOOTWAY":
                body += u"      " + random.choice(walkEmojis) + " laufen\n"
            else:
                body += addspaces(6) + build_label(part['product'], part['label']) + " " + part['destination'] + "\n"
            body += mvgtime_to_hrs(part['arrival']) + " - " + to_name + "\n"
    msg=body
    return msg

def plan(bot, update, edit = False):
    split = "planCategoryId|split|"
    row = 0
    buttons = []
    for category in plans:
        buttons.append([])
        callback_data = split+str(category['category_id'])
        buttons[row].append(InlineKeyboardButton(category['name'], callback_data=callback_data))
        row += 1
    if edit:
        bot.editMessageText(chat_id=update.message.chat_id,  text="Wähle eine Kategorie aus:", reply_markup=InlineKeyboardMarkup(buttons), message_id=update.message.message_id)
        logger.info('Sending plan category select buttons to %s', update.from_user)
    else:
        logger.info('Sending plan category select buttons to %s', update.message.from_user)
        bot.sendMessage(update.message.chat_id, text="Wähle eine Kategorie aus:", reply_markup=InlineKeyboardMarkup(buttons))

def sendPlanCategory(bot, update, category_id):
    split = "planPlanId|split|"
    row = 0
    buttons = []
    category_name = plans[category_id]['name']
    for plan in plans[category_id]['content']:
        buttons.append([])
        callback_data = split+str(plan['plan_id'])+"|wurst|"+str(category_id)
        buttons[row].append(InlineKeyboardButton(plan['name'], callback_data=callback_data))
        row += 1
    buttons.append([])
    buttons[row].append(InlineKeyboardButton("< Zurück", callback_data="planBack|split|x"))
    bot.editMessageText(chat_id=update.message.chat_id, text="Wähle einen Plan ausd der Kategorie "+ category_name +":", reply_markup=InlineKeyboardMarkup(buttons), message_id=update.message.message_id)
    logger.info('Sending plan plan select buttons to %s', update.from_user)

def sendPlanPlan(bot, update, category_id, plan_id):
    file_id = plans[category_id]['content'][plan_id]['file_id']
    bot.editMessageText(chat_id=update.message.chat_id, text="Plan wird gesendet...", message_id=update.message.message_id)
    bot.send_document(update.message.chat_id, file_id)
    logger.info('Sending real plan select buttons to %s', update.from_user)

def name_for_route_part(part):
    try:
        return part['name']
    except KeyError:
        key = shortcutKeyForGps((part['latitude'],part['longitude']))
        if key == None:
            return str(part['latitude']) + ", " + str(part['longitude'])
        else:
            return shortcuts[key]['name']

def r(gps, d=3):
     return (round(gps[0],d),round(gps[1],d))

def build_label(part1,part2):
    return part2
    service = {'t': "", 'u': "U", 'b': "", 's': "S"}
    try:
        label = service[part1]
    except:
        label = part1
    label += str(part2)
    return label

def escape_markdown(text):
    """Helper function to escape telegram markup symbols"""
    escape_chars = '\*_`\['
    return re.sub(r'([%s])' % escape_chars, r'\\\1', text)

def addspaces(n, string=""):
    while n > 0:
        string=string+" "
        n=n-1
    return string

def findNotUsedEmoji():
    for k in emojiList:
        if not k in shortcuts:
            return k

def addShortcut(bot, update, lat, lon, short=False, name=""):
    key = shortcutKeyForGps((lat,lon))
    if key == None:
        if not short:
            short = findNotUsedEmoji()
            shortcuts[short] = {"name": name.lower(), "gps": (lat,lon)}
            logger.info('%s saved new location %s.', update.message.from_user, short)
    else:
        short = key
        logger.info('%s tried to resave %s', update.message.from_user, short)

    msg = u"Du kannst nun mit '" + short + u"' temporär zu oder von diesem Standort Routen planen."
    bot.editMessageText(chat_id=update.message.chat_id, text=msg, message_id=update.message.message_id)

def shortcutKeyForGps(gps):
    for key, shortcut in shortcuts.items():
        if r(shortcut['gps']) == r((gps[0],gps[1])):
            return key
    return None

def mvgtime_to_hrs(time):
    dt = datetime.datetime.fromtimestamp(time/1000)
    time = dt.strftime("%H:%M")
    wday = dt.weekday()
    if not datetime.datetime.now().weekday() == wday:
        time = weekdays[wday] + " " + time
    return time

def datetime_to_mvgtime(dtime):
    time = int(dtime.strftime("%s"))*1000
    return time

def error(bot, update, error):
    logger.warning('Update "%s" caused error "%s"' % (update, error))

def main():
    logger.info("Starting")
    dp = updater.dispatcher #not double penetration

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("plan", plan))
    dp.add_handler(CommandHandler("help", help))
    dp.add_handler(MessageHandler(Filters.location, gps))
    dp.add_handler(MessageHandler(Filters.text, msg))
    dp.add_handler(CallbackQueryHandler(buttonHandler))

    dp.add_error_handler(error)

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
