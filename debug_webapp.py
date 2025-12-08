
with open('/home/justin/code/twitter-futzing/webapp.py', 'r') as f:
    lines = f.readlines()
    
# Print lines around 1570
print("Lines 1568-1580:")
for i in range(1568, 1581):
    print(f"{i+1}: {repr(lines[i])}")
