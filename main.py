import os
import hashlib
import time
from tkinter import *
from tkinter import messagebox
import json
import threading
import psutil


foldconfig = "C:/Users/User/AppData/Roaming/cleaner/config.json"
allowed = list()
actived = 0
py = 0

with open(foldconfig, "r") as f:
    config = json.load(f)

if config["blocked"] is None:
    config["blocked"] = list()


while True:
    with open(foldconfig, "r") as f:
        config = json.load(f)
    if config["blocked"] is None:
        config["blocked"] = list()

    for i in allowed:
        if i not in os.listdir("c:/Users/User/Downloads/"):
            allowed.remove(i)

    for i in os.listdir("c:/Users/User/Downloads/"):
        if i not in allowed and actived == 0 and i.split(".")[-1] in config["blocked"]:
            def mainblock(prog: str):
                global allowed
                global actived
                file = i

                def sp():
                    if hashlib.sha1(hashlib.sha256(ent.get().encode()).hexdigest().encode()).hexdigest() == \
                            "f5a14bb722b14febaddea60a1256a4ca70deb524" \
                            or hashlib.sha1(hashlib.sha256(ent.get().encode()).hexdigest().encode()).hexdigest() == \
                            "3c8c6e9dd628dbc96982a06079393ecb231b69cf":
                        btn.pack_forget()
                        ent.pack_forget()
                        wm.destroy()
                        time.sleep(0.5)
                        os.system('start explorer.exe')
                        messagebox.showinfo("Информация", "Приятного использования!")
                        allowed.append(prog)
                        actived = 0
                    else:
                        ent.delete(0, END)
                        ent.insert(0, "")
                        ent.focus()

                def delfile():
                    try:
                        os.remove("c:/Users/User/Downloads/"+file)
                        time.sleep(1)
                        btn.pack_forget()
                        btndel.place_forget()
                        ent.pack_forget()
                        wm.destroy()
                        time.sleep(0.5)
                        os.system('start explorer.exe')
                        messagebox.showinfo("Информация", "Приятного использования!")
                        actived = 0
                    except:
                        messagebox.showerror("Ошибка", "Не удалось удалить файл")
                try:
                    os.system('taskkill /f /im explorer.exe')
                except:
                    pass
                time.sleep(1)

                wm = Tk()
                wm.overrideredirect(1)
                wm.state('zoomed')

                def on_closing():
                    pass

                wm.protocol("WM_DELETE_WINDOW", on_closing)
                wm.protocol()

                lb = Label(wm, text="    Компьютер заблокирован    ", font="Arial 75", fg="black")
                info = Label(wm, text="Разблокировать может только Админ", font="Arial 35", fg="black")
                infotext = Label(wm, text="Причина блокировки: скачивание exe/msi файла", font="Arial 35", fg="black")
                btn = Button(wm, width=15, height=1, text="Разблокировать", command=sp, bd=0, fg='#fff', bg='#08f',
                                activebackground='#fff', activeforeground='#fff', cursor='hand2', relief=RIDGE)
                ent = Entry(width=30, show='*')
                btndel = Button(wm, width=30, height=2, text="Удалить файл", command=delfile, bd=0, fg='#fff', bg='#08f',
                                activebackground='#fff', activeforeground='#fff', cursor='hand2', relief=RIDGE)

                btndel.place(relx=.5, rely=.5, anchor="c")
                lb.pack()
                info.pack()
                infotext.pack()
                ent.pack(pady=10)
                ent.focus()
                btn.pack()

                wm.lift()
                wm.attributes('-topmost', True)
                wm.attributes('-alpha', 0.8)
                wm.after_idle(wm.attributes, '-topmost', True)
                wm.mainloop()
            threading.Thread(target=mainblock, args=(i,)).start()
            actived = 1
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info["name"] == "pyw.exe":
            py += 1
    if py < 2:
        os.startfile("C:/Users/User/AppData/Roaming/cleaner/monitorer.pyw")
        time.sleep(0.33)
    else:
        py = 0
