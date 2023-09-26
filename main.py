import os
import hashlib
import time
from tkinter import *
from tkinter import messagebox
import json
import threading


with open("config.json") as f:
    config = json.load(f)

if config["allowed"] is None:
    config["allowed"] = list()

if config["blocked"] is None:
    config["blocked"] = list()


def ews(key: str, value):
    config[key] = value
    with open("config.json", "w") as f:
        json.dump(config, f)


ews("actived", 0)

while True:
    with open("config.json") as f:
        config = json.load(f)

    if config["allowed"] != None:
        for i in config["allowed"]:
            if i not in os.listdir("c:/Users/User/Downloads/"):
                config["allowed"].remove(i)
                ews("allowed", config["allowed"])

    for i in os.listdir("c:/Users/User/Downloads/"):
        if (not config["allowed"] or i not in config["allowed"]) and config["actived"] == 0 and i.split(".")[-1] in config["blocked"]:
            def maint(prog: str):
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
                        config["allowed"].append(prog)
                        ews("allowed", config["allowed"])
                        ews("actived", 0)
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
                        ews("actived", 0)
                    except:
                        messagebox.showerror("Ошибка", "Не удалось удалить файл")

                os.system('taskkill /f /im explorer.exe')
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
            threading.Thread(target=maint, args=(i,)).start()
            ews("actived", 1)
    time.sleep(0.1)
