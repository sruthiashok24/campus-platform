CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('student','admin')),
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE events (
  id SERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT,
  category TEXT NOT NULL DEFAULT 'Event',
  venue TEXT,
  event_date DATE NOT NULL,
  capacity INT NOT NULL DEFAULT 100 CHECK (capacity > 0),
  created_by INT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE registrations (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event_id INT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, event_id)
);

CREATE TABLE resources (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  quantity INT NOT NULL DEFAULT 1 CHECK (quantity >= 1)
);

CREATE TABLE allocations (
  id SERIAL PRIMARY KEY,
  event_id INT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  resource_id INT NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
  quantity INT NOT NULL CHECK (quantity > 0),
  UNIQUE (event_id, resource_id)
);

CREATE TABLE notifications (
  id SERIAL PRIMARY KEY,
  user_email TEXT NOT NULL,
  message TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

INSERT INTO events (title, description, category, venue, event_date, capacity) VALUES
 ('Hackathon 2026', '24-hour coding challenge with prizes', 'Hackathon', 'Innovation Lab', '2026-11-15', 120),
 ('Cloud Workshop', 'Hands-on Docker and Azure session', 'Workshop', 'Computer Lab 3', '2026-11-20', 60),
 ('AI Seminar', 'Guest talk on applied machine learning', 'Seminar', 'Seminar Hall A', '2026-12-02', 200),
 ('Placement Prep Webinar', 'Resume and interview tips from alumni', 'Webinar', 'Online', '2026-12-10', 500);

INSERT INTO resources (name, type, quantity) VALUES
 ('Seminar Hall A', 'Hall', 1),
 ('Projector', 'Equipment', 6),
 ('Computer Lab 3', 'Lab', 2),
 ('Wireless Mic', 'Equipment', 4);
