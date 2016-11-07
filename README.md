# Transfer

This helps you transfer data from pythonista to pythonista and PC to pythonista and PC to PC.

Your device must be in local network
#Feature
1.Auto scaning server

So you need not search your ip

2.Sharing text

You can share text

3.Starting up

Your device can be ready to receive when starting up.
Add following code to site-packages-2/pythonista_startup.py *not 3 but 2*

~~~~
import Transfer

Transfer.start_up()
~~~~

#How to set up
1.Make three shortcuts

Run script : Transfer.py

     A.
     Argumets :

     Title : Send this file

     B.
     Arguments : send_selected_or_clipboard_text

     Title : Send text

     C.
     Arguments : receive
     
     Title : Receive

2.Make two Extension Shortcuts
     
     A.
     Arguments : 

     Title : Send this file/text

     B.
     Arguments : send_selected_or_clipboard_text
     
     Title : Send clipboard text

#How to use 
