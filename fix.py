import re

with open("main.py", "r") as f:
    data = f.read()

# Fix the indentation of the else statement that got messed up by sed
data = data.replace('                                    else:', '                                else:')

with open("main.py", "w") as f:
    f.write(data)
