import sqlite3
paths = [r'R:\\ArkDiscordBot\\bot.db', r'R:\\ArkDiscordBot\\ark_bot.db']
for path in paths:
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.execute("SELECT id,guild_id,name,host,game_port,query_port,rcon_port,service_name,log_path FROM server_ark_servers ORDER BY name")
        rows = cur.fetchall()
        print('\nDB:', path)
        if not rows:
            print('  No rows')
        else:
            for r in rows:
                print(' ', r)
        conn.close()
    except Exception as e:
        print('Error reading', path, e)
