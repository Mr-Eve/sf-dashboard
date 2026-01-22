#!/usr/bin/env python3
import sqlite3
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = '8489199162:AAH3I-YllaSCbzCJ4oL3cYtLVnOJ7G3deNM'

def init_database():
    db = sqlite3.connect('events.db')
    db.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            date_display TEXT NOT NULL,
            event_date TEXT NOT NULL,
            time TEXT
        )
    ''')
    db.commit()
    db.close()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command"""
    try:
        welcome_message = (
            "👋 Welcome to the SF Dashboard Bot!\n\n"
            "Available commands:\n"
            "• /add <day> <time> <title> - Add an event\n"
            "• /list - Show all upcoming events\n"
            "• /delete <keywords> - Delete events\n"
            "• /clear - Clear all events\n\n"
            "Examples:\n"
            "/add Tue 2pm Team meeting\n"
            "/add Tomorrow 9am Coffee\n"
            "/add Sep-24 3pm Dentist"
        )
        await update.message.reply_text(welcome_message)
    except Exception as e:
        print(f"Error in start_command: {e}")
        try:
            await update.message.reply_text("Welcome! Use /list to see available commands.")
        except:
            pass

async def add_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) < 3:
            await update.message.reply_text(
                'Usage: /add <day> <time> <title>\n'
                'Examples:\n'
                '/add Tue 2pm Team meeting\n'
                '/add Sep-24 3pm Dentist\n'
                '/add Oct-1 none Return flight\n'
                '/add Tomorrow 9am Coffee with Bob'
            )
            return
        
        day_input = context.args[0]
        time_input = context.args[1] if context.args[1].lower() != 'none' else ''
        title = ' '.join(context.args[2:])
        
        today = datetime.now()
        days_map = {
            'mon':0,'tue':1,'wed':2,'thu':3,'fri':4,'sat':5,'sun':6,
            'monday':0,'tuesday':1,'wednesday':2,'thursday':3,'friday':4,'saturday':5,'sunday':6
        }
        
        event_date = None
        day_lower = day_input.lower()
        
        if day_lower in days_map:
            days_ahead = days_map[day_lower] - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            event_date = today + timedelta(days=days_ahead)
        elif day_lower == 'tomorrow':
            event_date = today + timedelta(days=1)
        elif day_lower == 'today':
            event_date = today
        else:
            try:
                if '-' in day_input:
                    parts = day_input.split('-')
                    if len(parts) == 2:
                        month_str = parts[0]
                        day_str = parts[1]
                        
                        months = {
                            'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,
                            'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12,
                            'january':1,'february':2,'march':3,'april':4,'may':5,'june':6,
                            'july':7,'august':8,'september':9,'october':10,'november':11,'december':12
                        }
                        
                        month = months.get(month_str.lower())
                        if month:
                            day = int(day_str)
                            year = today.year
                            test_date = datetime(year, month, day)
                            if test_date.date() < today.date():
                                year += 1
                            event_date = datetime(year, month, day)
            except:
                pass
        
        if not event_date:
            await update.message.reply_text('Invalid date format')
            return
        
        days_difference = (event_date.date() - today.date()).days
        if days_difference > 7:
            await update.message.reply_text(f'Event is {days_difference} days away. Only showing events within next 7 days on dashboard.')
        
        date_display = event_date.strftime('%a %b %d')
        if time_input:
            date_display += f' {time_input}'
        
        sql_date = event_date.strftime('%Y-%m-%d')
        
        db = sqlite3.connect('events.db')
        db.execute('INSERT INTO events (title, date_display, event_date, time) VALUES (?, ?, ?, ?)', 
                   (title, date_display, sql_date, time_input))
        db.commit()
        db.close()
        
        await update.message.reply_text(f'Added: {date_display} - {title}')
    
    except Exception as e:
        print(f"Error in add_event: {e}")
        import traceback
        traceback.print_exc()
        await update.message.reply_text('Sorry, there was an error adding your event. Please try again.')

async def list_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        db = sqlite3.connect('events.db')
        cur = db.execute('''
            SELECT date_display, title, event_date 
            FROM events 
            WHERE event_date >= date('now') 
            ORDER BY event_date, time 
            LIMIT 20
        ''')
        events = cur.fetchall()
        db.close()
        
        if not events:
            await update.message.reply_text('No upcoming events')
        else:
            msg = 'Upcoming events:\n'
            for e in events:
                days_away = (datetime.strptime(e[2], '%Y-%m-%d').date() - datetime.now().date()).days
                msg += f'{e[0]}: {e[1]} ({days_away} days)\n'
            await update.message.reply_text(msg)
    
    except Exception as e:
        print(f"Error in list_events: {e}")
        import traceback
        traceback.print_exc()
        await update.message.reply_text('Sorry, there was an error retrieving events. Please try again.')

async def delete_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text('Usage: /delete <title keywords>')
            return
        
        search = ' '.join(context.args)
        db = sqlite3.connect('events.db')
        db.execute('DELETE FROM events WHERE title LIKE ?', (f'%{search}%',))
        deleted = db.total_changes
        db.commit()
        db.close()
        
        if deleted:
            await update.message.reply_text(f'Deleted {deleted} event(s)')
        else:
            await update.message.reply_text('No matching events found')
    
    except Exception as e:
        await update.message.reply_text('Sorry, there was an error deleting the event. Please try again.')

async def clear_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        db = sqlite3.connect('events.db')
        db.execute('DELETE FROM events')
        db.commit()
        db.close()
        await update.message.reply_text('All events cleared')
    
    except Exception as e:
        await update.message.reply_text('Sorry, there was an error clearing events. Please try again.')

def main():
    init_database()
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("add", add_event))
    app.add_handler(CommandHandler("list", list_events))
    app.add_handler(CommandHandler("delete", delete_event))
    app.add_handler(CommandHandler("clear", clear_all))
    
    print("Bot starting...")
    print("Bot is ready! Send /list to see commands.")
    print("Waiting for messages...")
    try:
        app.run_polling(drop_pending_updates=True)
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()