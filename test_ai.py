from dotenv import load_dotenv
load_dotenv()  # must come before importing analyzer

from analyzer import analyze_resume

sample = """
John Doe
Python developer with 2 years experience building Flask APIs and React apps.
Built a chat app used by 300 students.
Skills: Python, Flask, React, SQL.
Education: BS Computer Science
"""

result = analyze_resume(sample, "Backend developer")
for key, value in result.items():
    print(key, ":", value)