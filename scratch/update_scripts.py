import re

files_to_update = [
    "follow_mam.py",
    "mam_management/change_mam_category.py",
    "dashboard_server.py"
]

for file_path in files_to_update:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Replace
        new_content = content.replace("mammaster@mailinator.com", "mamm@mailinator.com")
        new_content = new_content.replace("Test@1234", "12345678")
        new_content = re.sub(r'DEFAULT_EMAIL_PREFIX\s*=\s*["\']mamfollower["\']', 'DEFAULT_EMAIL_PREFIX = "mamf"', new_content)
        new_content = re.sub(r'DEFAULT_PREFIX\s*=\s*["\']mamfollower["\']', 'DEFAULT_PREFIX = "mamf"', new_content)
        
        if new_content != content:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            print("Updated:", file_path)
    except Exception as e:
        print("Error on", file_path, e)
