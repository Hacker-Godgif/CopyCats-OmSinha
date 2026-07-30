"""
Sample Generator for StudyOS-India.
Creates test files: clean syllabus, messy scanned timetable, clean attendance CSV, malformed attendance CSV, exam datesheet.
"""

import os


def generate_samples(target_dir: str = "."):
    os.makedirs(target_dir, exist_ok=True)

    # 1. Clean Syllabus Text (Syllabus.txt)
    syllabus_content = """--- Page 1 ---
CS101: Computer Science Fundamentals Syllabus 2026

Course Overview:
Welcome to CS101. Below are the mandatory course deadlines for Fall 2026.

Important Deadlines:
1. Programming Assignment 1 submission due on 15/08/2026
2. Quiz 1 in-class test scheduled for 22-Aug-2026
3. Midterm Exam on 10th September 2026
4. Programming Assignment 2 submission deadline: 25/09/2026

--- Page 2 ---
5. Mini-Project Proposal submission due on 05-10-2026
6. Lab Report 1 submission due on 18th October 2026
7. Quiz 2 online test due on 28/10/2026
8. Mini-Project Final Code submission due on 15-Nov-2026
9. Lab Report 2 submission deadline: 25th November 2026
10. Final Project Presentation and Viva due on 05/12/2026
"""

    # 2. Scanned / Messy Timetable
    messy_timetable_content = """=== TIMETABLE BATCH 2026 (SCANNED COPY) ===
# WARNING: Image OCR Quality 42% (Low Confidence)
MON 09:00AM CS101_Lec #$@ room 302
TUE 11:30AM MATH201_Lab %^& room 104
WED TBD - Schedule to be announced
THU @#$%^&*()_+= ROTATED TEXT DETECTED UNREADABLE
FRI 02:00PM CS204_Viva room 201
"""

    # 3. Clean Attendance CSV
    clean_attendance_csv = """Course,Conducted_Classes,Attended_Classes
CS101 - Computer Science,40,36
MATH201 - Advanced Mathematics,35,28
CS204 - Database Management,30,27
CS302 - Operating Systems,45,40
"""

    # 4. Malformed Attendance CSV
    malformed_attendance_csv = """Course,Conducted_Classes,Attended_Classes
CS101 - Computer Science,40,45
MATH201 - Advanced Mathematics,0,5
CS204 - Database Management,-10,20
CS302 - Operating Systems,invalid_num,30
"""

    # 5. Exam Datesheet
    datesheet_content = """STUDYOS-INDIA END-TERM EXAM DATESHEET FALL 2026
Class ID: CSE-2026-A
Term Start: 2026-11-01

Exam Schedule:
1. CS101 Computer Science Fundamentals - Date: 05/11/2026
2. MATH201 Advanced Mathematics - Date: 08/11/2026
3. CS204 Database Management Systems - Date: 09/11/2026
4. CS302 Operating Systems - Date: 14/11/2026
"""

    files = {
        "sample_syllabus.txt": syllabus_content,
        "sample_scanned_timetable.txt": messy_timetable_content,
        "sample_attendance_clean.csv": clean_attendance_csv,
        "sample_attendance_malformed.csv": malformed_attendance_csv,
        "sample_datesheet.txt": datesheet_content
    }

    for fname, content in files.items():
        path = os.path.join(target_dir, fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    print(f"Successfully generated sample test files in {target_dir}")

if __name__ == "__main__":
    generate_samples()
