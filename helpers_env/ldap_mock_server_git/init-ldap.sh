#!/bin/bash
load_data() {
    echo "Background task: Waiting for LDAP to be ready..."
    for i in {1..30}; do
        # Use ldapsearch as a health probe
        if ldapsearch -x -H ldap://localhost:389 -s base -b "" > /dev/null 2>&1; then
            echo "LDAP is up! Loading data..."
            ldapadd -c -x -H ldap://localhost:389 -D "cn=admin,dc=mock,dc=com" -w testpass -f /container/service/slapd/assets/data/01-ou.ldif
            ldapadd -c -x -H ldap://localhost:389 -D "cn=admin,dc=mock,dc=com" -w testpass -f /container/service/slapd/assets/data/02-users.ldif
            echo "Data initialization complete."
            return 0
        fi
        sleep 1
    done
}
load_data &
exit 0
