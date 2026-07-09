import pymysql

db_config = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "Yyc060501",
    "charset": "utf8mb4"
}

conn = pymysql.connect(**db_config)
cursor = conn.cursor()

try:
    cursor.execute("CREATE DATABASE IF NOT EXISTS move_car DEFAULT CHARACTER SET utf8mb4;")
    print("✅ 数据库 move_car 创建成功")
except Exception as e:
    print("❌ 创建失败：", e)
finally:
    cursor.close()
    conn.close()
