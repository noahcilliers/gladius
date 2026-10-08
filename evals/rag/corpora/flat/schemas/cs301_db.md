```sql
CREATE TABLE students (
  id INT PRIMARY KEY,
  name TEXT,
  major TEXT,
  year INT,
  gpa REAL
);

CREATE TABLE courses (
  id INT PRIMARY KEY,
  code TEXT,          -- e.g. 'CS 301'
  title TEXT,
  instructor TEXT,
  credits INT
);

CREATE TABLE enrollments (
  student_id INT REFERENCES students(id),
  course_id INT REFERENCES courses(id),
  semester TEXT,      -- e.g. 'Fall 2026'
  grade TEXT,         -- letter grade, NULL if in progress
  PRIMARY KEY (student_id, course_id, semester)
);
```

```sql
CREATE TABLE stations (
  id INT PRIMARY KEY,
  name TEXT,
  capacity INT
);

CREATE TABLE bikes (
  id INT PRIMARY KEY,
  status TEXT,        -- 'available', 'in_use', 'maintenance'
  home_station_id INT REFERENCES stations(id)
);

CREATE TABLE riders (
  id INT PRIMARY KEY,
  student_id INT,
  joined_at DATE
);

CREATE TABLE rides (
  id INT PRIMARY KEY,
  bike_id INT REFERENCES bikes(id),
  rider_id INT REFERENCES riders(id),
  start_station_id INT REFERENCES stations(id),
  end_station_id INT REFERENCES stations(id),
  started_at TIMESTAMP,
  ended_at TIMESTAMP
);
```
