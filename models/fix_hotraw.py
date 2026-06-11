"""
Fix base hot_raw to be at least 1.
Usage: python fix_hotraw.py
Requires: sshpass or manual SSH config.
"""
import subprocess
import os

# The fix: change hot_raw calculation to use greatest(..., lit(1))
OLD_LINE = '''    val withHotRaw = df.withColumn("hot_raw",
      col("like_count") + col("comment_count") +
      col("coin_count") + col("favorite_count") + col("share_count")
    )'''

NEW_LINE = '''    val withHotRaw = df.withColumn("hot_raw",
      greatest(
        col("like_count") + col("comment_count") +
        col("coin_count") + col("favorite_count") + col("share_count"),
        lit(1)
      )
    )'''

FILE = "/home/<USER>/deploy_files/src/main/scala/com/example/cleaner/DataCleanerUtils.scala"

# Use sed for single-line replacement (simpler escaping)
# Match the multi-line pattern by using sed with hold space
script = f'''
ssh -i <SSH_KEY_PATH> root@<INTRANET_IP> << 'REMOTE'
cd /home/<USER>/deploy_files
python3 -c "
f = '{FILE}'
with open(f) as fp:
    c = fp.read()
old = '{OLD_LINE}'
new = '{NEW_LINE}'
if old in c:
    c = c.replace(old, new)
    with open(f, 'w') as fp:
        fp.write(c)
    print('SUCCESS: hot_raw base=1 applied')
else:
    print('FAIL: old pattern not found')
    import re
    m = re.search(r'val withHotRaw.*?\\n    \\)', c, re.DOTALL)
    if m:
        print('Found current code:')
        print(repr(m.group()))
"
REMOTE
'''

result = subprocess.run(
    ["ssh", "-i", "<SSH_KEY_PATH>", "root@<SERVER_IP>"],
    input=script,
    capture_output=True,
    text=True,
    timeout=30
)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr[:500])
