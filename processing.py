import datetime
import json
import os
import tempfile
import urllib.request

import cv2
import numpy
from telebot import types

import config


def prepare_url(msg):
    file_id_url = 'https://api.telegram.org/bot<bot_token>/getFile?file_id=<the_file_id>'
    result = json.load(urllib.request.urlopen(file_id_url
                                              .replace('<bot_token>',
                                                       str(config.token))
                                              .replace('<the_file_id>',
                                                       str(msg.photo[len(msg.photo) - 1].file_id))))['result']
    file_path = result['file_path']
    file_path_url = 'https://api.telegram.org/file/bot<token>/<file_path>'
    return file_path_url \
        .replace('<token>', config.token) \
        .replace('<file_path>', file_path)


def url_to_cv2(url):
    result = url_to_image(url)
    image = numpy.asarray(bytearray(result), dtype="uint8")
    image = cv2.imdecode(image, cv2.IMREAD_COLOR)
    return image


def url_to_image(url):
    response = urllib.request.urlopen(url)
    return response.read()


def process_photo_message(message, usr, detector, bot, original_mat, path_delta):
    # TODO remove black magic
    cv_mat = original_mat
    cv_mat = detector.detect_head(cv_mat, usr)
    tmp_file = tempfile.TemporaryFile("w+b")
    if cv_mat is not None:
        write_log(datetime.datetime.now().isoformat(),
                  message.chat.id,
                  message.chat.first_name,
                  message.chat.last_name,
                  message.chat.username,
                  "http://%s:%s/original/?id=%s" % (config.WEBHOOK_HOST, config.IMAGES_PORT, path_delta),
                  "face was found, will send it to user, try %d" % usr.tries)
        encoded_image = cv2.imencode(ext='.png', img=cv_mat)[1]
        tmp_file.write(encoded_image)
        keyboard = types.InlineKeyboardMarkup()
        callback_true = types.InlineKeyboardButton(text="Всё верно", callback_data="true")
        callback_false = types.InlineKeyboardButton(text="Есть ошибка", callback_data="false")
        keyboard.add(callback_true)
        keyboard.add(callback_false)
        tmp_file.seek(0)
        bot.send_photo(message.chat.id, tmp_file, reply_markup=keyboard)
        detector.default_haarcascade_for_user(usr)
        tmp_file.close()
    elif usr.tries >= len(detector.haarcascades) - 1 or usr.tries >= len(detector.haarcascades) - 1 and cv_mat is None:
        write_log(datetime.datetime.now().isoformat(),
                  message.chat.id,
                  message.chat.first_name,
                  message.chat.last_name,
                  message.chat.username,
                  "http://%s:%s/original/?id=%s" % (config.WEBHOOK_HOST, config.IMAGES_PORT, path_delta),
                  "exceeded his tries and face wasn\'t found, try %d" % usr.tries)
        usr.tries = 0
        detector.default_haarcascade_for_user(usr)
        bot.send_message(message.chat.id, "Лицо не найдено, попробуйте другую фотографию")
        tmp_file.close()
    elif cv_mat is None:
        write_log(datetime.datetime.now().isoformat(),
                  message.chat.id,
                  message.chat.first_name,
                  message.chat.last_name,
                  message.chat.username,
                  "http://%s:%s/original/?id=%s" % (config.WEBHOOK_HOST, config.IMAGES_PORT, path_delta),
                  "face wasn\'t found, try %d" % usr.tries)
        detector.next_haarcascade_for_user(usr)
        tmp_file.close()
        process_photo_message(message, usr, detector, bot, original_mat, path_delta)


# <время> <тип_события> <id_беседы <имя> <фамилия> <username> <язык> <сообщение>
def write_log(time, id, firstname, lastname, username, url, message):  # TODO save url
    log_message = "%s %d %s %s %s %s %s\n" % \
                  (time, id, firstname, lastname, username, url, message)
    with open("log.txt", "a") as log:
        log.write(log_message)


def generate_current_path(dir, chat_id):
    chat_id = str(chat_id)
    old = [ele for ele in os.listdir(dir)
           if ele.startswith(chat_id)]
    last = sorted([ele.replace(chat_id + "_", "")
                  .replace(".png", "") for ele in old])[-1]
    path_delta = chat_id + "_" + last + '.png'
    return path_delta


def generate_next_path(dir, chat_id):
    chat_id = str(chat_id)
    old = [ele for ele in os.listdir(dir)
           if ele.startswith(chat_id)]
    if len(old) == 0:
        path_delta = chat_id + "_0" + '.png'
    else:
        last = sorted([ele.replace(chat_id + "_", "")
                      .replace(".png", "") for ele in old])[-1]
        path_delta = chat_id + "_" + str(int(last) + 1) + '.png'
    return path_delta
