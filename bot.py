# -*- coding: utf-8 -*-
import datetime
import logging

import cherrypy
import cv2
import telebot

import config
import processing
from detector import Detector
from processing import prepare_url, url_to_cv2, process_photo_message
from user import user

# initialization
logger = telebot.logger
telebot.logger.setLevel(logging.INFO)
bot = telebot.TeleBot(config.token)


# WebhookServer, process webhook calls
class WebhookServer(object):
    @cherrypy.expose
    def index(self):
        if 'content-length' in cherrypy.request.headers and \
                'content-type' in cherrypy.request.headers and \
                cherrypy.request.headers['content-type'] == 'application/json':
            length = int(cherrypy.request.headers['content-length'])
            json_string = cherrypy.request.body.read(length).decode("utf-8")
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return ''
        else:
            raise cherrypy.HTTPError(403)


detector = Detector()
users = []


# handlers
@bot.message_handler(content_types=["text"])
def repeat_all_text(message):
    pass
    # bot.send_message(message.chat.id, "Пришлите фотографию, исходя из которой нужно сделать фото профиля")


@bot.message_handler(func=lambda message: True, content_types=['photo'])
def photo(message, is_callback=False):
    cur_user: user = next((usr for usr in users if usr.chat_id == message.chat.id), False)

    cv_mat = url_to_cv2(prepare_url(message))
    path = '/root/profile_pics/originals/'
    if is_callback:
        path_delta = processing.generate_current_path(path, message.chat.id)
    else:
        path_delta = processing.generate_next_path(path, message.chat.id)
    cv2.imwrite(filename=path + path_delta,
                img=cv_mat)
    if not cur_user:
        cur_user = user(message.chat.id)
        users.append(cur_user)
    if is_callback:
        while not process_photo_message(message, cur_user, detector, bot, cv_mat, path_delta) \
                and cur_user.tries <= len(detector.haarcascades):
            pass
    else:
        process_photo_message(message, cur_user, detector, bot, cv_mat, path_delta)


# В большинстве случаев целесообразно разбить этот хэндлер на несколько маленьких
@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    # call.message.chat.id
    chat_id = call.message.chat.id
    # Если сообщение из чата с ботом
    if call.message:
        cur_user: user = next((usr for usr in users if usr.chat_id == call.message.chat.id), False)
        if not cur_user:
            return
        path = '/root/profile_pics/'
        if call.data == "true":
            path_delta = processing.generate_next_path(path, call.message.chat.id)
            cv2.imwrite(filename=path + path_delta,
                        img=url_to_cv2(prepare_url(call.message)))
            # bot.edit_message_text(text='', chat_id=chat_id, message_id=call.message.message_id)
            bot.send_message(chat_id, "Хорошо, приятно было с вами работать")
            processing.write_log(datetime.datetime.now().isoformat(),
                                 call.message.chat.id,
                                 call.from_user.first_name,
                                 call.from_user.last_name,
                                 call.from_user.username,
                                 "http://%s:%s/?id=%s" % (config.WEBHOOK_HOST, config.IMAGES_PORT, path_delta),
                                 "accepted our cropping")
            users.remove(cur_user)
            if cur_user:
                cur_user.tries = 0
        elif call.data == "false":
            if (cur_user.tries + 1 >= len(detector.haarcascades)):
                bot.send_message(chat_id, "К сожалению лицо не было найдено! Может попробуем другую фотографию?")

                users.remove(cur_user)
                # bot.edit_message_text(text='', chat_id=chat_id, message_id=call.message.message_id)
                cur_user.tries = 0
                processing.write_log(datetime.datetime.now().isoformat(),
                                     call.message.chat.id,
                                     call.from_user.first_name,
                                     call.from_user.last_name,
                                     call.from_user.username,
                                     '-',
                                     "didn\'t accept our cropping and he\'s ran out of tries")
            else:
                cv_mat = url_to_cv2(prepare_url(call.message))
                path = '/root/profile_pics/originals/'
                path_delta = processing.generate_current_path(path, call.message.chat.id)

                res_user = next(usr for usr in users if usr.chat_id == chat_id)
                detector.next_haarcascade_for_user(res_user)
                process_photo_message(call.message, cur_user, detector, bot, cv_mat, path_delta)
        bot.edit_message_reply_markup(chat_id, call.message.message_id)


# starting service

bot.remove_webhook()
bot.set_webhook(url=config.WEBHOOK_URL_BASE + config.WEBHOOK_URL_PATH,
                certificate=open(config.WEBHOOK_SSL_CERT, 'r'))
access_log = cherrypy.log.access_log
for handler in tuple(access_log.handlers):
    access_log.removeHandler(handler)
cherrypy.config.update({
    'server.socket_host': config.WEBHOOK_LISTEN,
    'server.socket_port': config.WEBHOOK_PORT,
    'server.ssl_module': 'builtin',
    'server.ssl_certificate': config.WEBHOOK_SSL_CERT,
    'server.ssl_private_key': config.WEBHOOK_SSL_PRIV
})
cherrypy.quickstart(WebhookServer(), config.WEBHOOK_URL_PATH, {'/': {}})
