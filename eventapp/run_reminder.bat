@echo off
cd /d "D:\event-management-and-tickets\EventSphere-TicketNest\backend\eventapp"
call ..\.venv\Scripts\activate.bat
system()
python manage.py notification
print("ad")
pause
