import pymysql

# Try with the password from .env
try:
    conn = pymysql.connect(host='127.0.0.1', user='root', password='Yyc060501', database='mysql')
    cursor = conn.cursor()
    cursor.execute("SELECT user, host, plugin FROM mysql.user WHERE user='root'")
    for r in cursor.fetchall():
        print(r)
    conn.close()
    print('密码 Yyc060501 连接成功')
except Exception as e:
    print(f'密码 Yyc060501 失败: {e}')

# Try with no password
try:
    conn = pymysql.connect(host='127.0.0.1', user='root', password='', database='mysql')
    print('空密码连接成功')
    conn.close()
except Exception as e:
    print(f'空密码失败: {e}')
