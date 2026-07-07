#!/bin/sh
set -eu

init_mysql() {
    mkdir -p /run/mysqld /var/lib/mysql
    chown mysql:mysql /run/mysqld /var/lib/mysql
    mysql_socket_args="--protocol=socket --host=localhost --socket=/run/mysqld/mysqld.sock -uroot"

    if [ -f /var/lib/mysql/.shiny-notes-initialized ]; then
        return
    fi

    if [ ! -d /var/lib/mysql/mysql ]; then
        mysql_install_db --user=mysql --datadir=/var/lib/mysql >/dev/null
    fi

    mysqld --user=mysql --skip-networking --skip-grant-tables &
    mysql_pid=$!

    ready=0
    for _ in $(seq 1 60); do
        if mysqladmin $mysql_socket_args ping --silent >/dev/null 2>&1; then
            ready=1
            break
        fi
        sleep 1
    done

    if [ "$ready" -ne 1 ]; then
        kill "$mysql_pid" 2>/dev/null || true
        wait "$mysql_pid" 2>/dev/null || true
        echo "mysql failed to start during initialization" >&2
        exit 1
    fi

    mysql $mysql_socket_args <<'SQL'
FLUSH PRIVILEGES;
CREATE DATABASE IF NOT EXISTS notes;
CREATE USER IF NOT EXISTS 'notes'@'localhost' IDENTIFIED BY 'notespw';
CREATE USER IF NOT EXISTS 'notes'@'127.0.0.1' IDENTIFIED BY 'notespw';
ALTER DATABASE notes CHARACTER SET = big5 COLLATE = big5_chinese_ci;
CREATE TABLE IF NOT EXISTS notes.users (
    username   VARCHAR(255) NOT NULL PRIMARY KEY,
    nonce      TEXT NOT NULL,
    ciphertext TEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=big5 COLLATE=big5_chinese_ci;
GRANT SELECT, INSERT, UPDATE ON notes.users TO 'notes'@'localhost';
GRANT SELECT, INSERT, UPDATE ON notes.users TO 'notes'@'127.0.0.1';
FLUSH PRIVILEGES;
SQL

    mysqladmin $mysql_socket_args shutdown
    wait "$mysql_pid"
    touch /var/lib/mysql/.shiny-notes-initialized
    chown mysql:mysql /var/lib/mysql/.shiny-notes-initialized
}

init_mysql
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
