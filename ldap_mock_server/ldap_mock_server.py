import uuid

class MockLDAPServer:
    """
    A simple in-memory mock LDAP directory for user management.
    Keys are the user's distinguished name (DN).
    """

    def __init__(self):
        # Key: DN (e.g., "cn=alice,ou=users,dc=example,dc=com")
        # Value: A dictionary of user attributes
        self.directory = {}
        print("Mock LDAP Server Initialized.")

    def _generate_dn(self, username):
        """Generates a standard DN for a user."""
        return f"cn={username},ou=users,dc=mock,dc=com"

    # --- CRUD Operations ---

    def create_user(self, username, attributes=None):
        """Adds a new user to the directory."""
        dn = self._generate_dn(username)
        
        if dn in self.directory:
            print(f"ERROR: User '{username}' already exists.")
            return False

        user_data = {
            'cn': [username],
            'uid': [username],
            'objectClass': ['inetOrgPerson', 'person', 'top'],
            'sn': [username.capitalize()],
        }
        
        # Add or override any custom attributes
        if attributes:
            user_data.update(attributes)
            
        # Add a unique ID for simulation purposes
        if 'entryUUID' not in user_data:
            user_data['entryUUID'] = [str(uuid.uuid4())]

        self.directory[dn] = user_data
        print(f"SUCCESS: User '{username}' created with DN: {dn}")
        return True

    def delete_user(self, username):
        """Removes a user from the directory."""
        dn = self._generate_dn(username)
        
        if dn in self.directory:
            del self.directory[dn]
            print(f"SUCCESS: User '{username}' (DN: {dn}) deleted.")
            return True
        else:
            print(f"ERROR: User '{username}' not found.")
            return False

    def list_users(self, search_filter='(objectClass=*)', base_dn="dc=mock,dc=com"):
        """
        Simulates an LDAP search operation.
        Note: This mock only supports listing all users, not filter parsing.
        """
        results = []
        print(f"\n--- Listing Users (Search Base: {base_dn}, Filter: {search_filter}) ---")
        
        for dn, attributes in self.directory.items():
            # A real LDAP server would parse the filter and base_dn
            if dn.endswith(base_dn):
                results.append({'dn': dn, 'attributes': attributes})

        print(f"Found {len(results)} users.")
        return results

# --- Example Usage ---
if __name__ == "__main__":
    ldap_mock = MockLDAPServer()
    print("-" * 30)

    # 1. CREATE USERS
    ldap_mock.create_user("alice")
    ldap_mock.create_user("bob", {"mail": ["bob@mock.com"], "telephoneNumber": ["555-1234"]})
    ldap_mock.create_user("charlie")
    print("-" * 30)

    # 2. LIST USERS
    all_users = ldap_mock.list_users()
    for user in all_users:
        print(f"DN: {user['dn']}")
        print(f"  CN: {user['attributes'].get('cn', ['N/A'])[0]}")
        print(f"  Mail: {user['attributes'].get('mail', ['N/A'])[0]}")
        print("-" * 10)
        
    print("-" * 30)

    # 3. DELETE A USER
    ldap_mock.delete_user("alice")
    ldap_mock.delete_user("diana") # Attempt to delete a non-existent user
    print("-" * 30)
    
    # 4. VERIFY DELETION (LIST AGAIN)
    remaining_users = ldap_mock.list_users()
    for user in remaining_users:
        print(f"Remaining User: {user['dn']}")
