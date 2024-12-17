db = db.getSiblingDB('admin');

if (db.system.users.find({ user: "root" }).count() === 0) {
  db.createUser({
    user: "root",
    pwd: "Hialeah2024*-",
    roles: [{ role: "root", db: "admin" }]
  });
}

db = db.getSiblingDB('db_main_load_data');

if (db.system.users.find({ user: "dbuser" }).count() === 0) {
  db.createUser({
    user: "test",
    pwd: "Hialeah2024*-",
    roles: [
      { role: "readWrite", db: "db_main_load_data" },
      { role: "dbAdmin", db: "db_main_load_data" }
    ]
  });
}

// db.createCollection("predictions_assessments");
// db.createCollection("predictions_vle");
// db.createCollection("predictions_risks");
db.login.insertOne({ user: "test", password: "Hialeah2024*-" });