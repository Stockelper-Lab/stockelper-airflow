// Initialize stockhelper database
db = db.getSiblingDB('stockelper');

// Create a sample collection to ensure database is created
db.createCollection('config');

print('Database stockhelper initialized successfully');

