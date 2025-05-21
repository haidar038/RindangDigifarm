from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import pymysql
import os
from datetime import datetime

# Import the app and db from the main application
from App import app, db

def run_migration():
    """Add confirmed_on column to users table if it doesn't exist"""
    with app.app_context():
        try:
            # Connect directly using pymysql to execute the ALTER TABLE statement
            # Get database connection details from app config
            db_uri = app.config['SQLALCHEMY_DATABASE_URI']
            
            # Parse the URI to get connection details
            # Format: mysql+pymysql://username:password@host:port/database
            parts = db_uri.replace('mysql+pymysql://', '').split('/')
            connection_string = parts[0]
            database = parts[1]
            
            if '@' in connection_string:
                auth, host = connection_string.split('@')
                username, password = auth.split(':')
            else:
                host = connection_string
                username = password = ''
                
            if ':' in host:
                host, port = host.split(':')
                port = int(port)
            else:
                port = 3306
                
            # Connect to the database
            connection = pymysql.connect(
                host=host,
                user=username,
                password=password,
                database=database,
                port=port
            )
            
            try:
                with connection.cursor() as cursor:
                    # Check if column exists
                    cursor.execute("""
                        SELECT COUNT(*) 
                        FROM information_schema.COLUMNS 
                        WHERE TABLE_SCHEMA = %s 
                        AND TABLE_NAME = 'users' 
                        AND COLUMN_NAME = 'confirmed_on'
                    """, (database,))
                    
                    if cursor.fetchone()[0] == 0:
                        # Column doesn't exist, add it
                        print("Adding 'confirmed_on' column to users table...")
                        cursor.execute("""
                            ALTER TABLE users 
                            ADD COLUMN confirmed_on DATETIME NULL
                        """)
                        
                        # Update confirmed_on for users that are already confirmed
                        cursor.execute("""
                            UPDATE users 
                            SET confirmed_on = %s 
                            WHERE is_confirmed = 1 AND confirmed_on IS NULL
                        """, (datetime.now(),))
                        
                        connection.commit()
                        print("Column 'confirmed_on' added successfully.")
                    else:
                        print("Column 'confirmed_on' already exists in users table.")
            finally:
                connection.close()
                
        except Exception as e:
            print(f"Error during migration: {e}")
            
if __name__ == '__main__':
    run_migration()
