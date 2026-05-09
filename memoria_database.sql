-- user and profile management

CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    pass VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL CHECK (role IN ('patient', 'caregiver', 'admin', 'family')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);

CREATE TABLE patients (
    patient_id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    date_of_birth DATE,
    gender VARCHAR(20),
    emergency_contact VARCHAR(20),
    emergency_contact_name VARCHAR(100),
    address TEXT,
    medical_history JSONB,
    dementia_stage VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_patients_user_id ON patients(user_id);

CREATE TABLE caregivers (
    caregiver_id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    phone VARCHAR(20),
    specialization VARCHAR(100),
    license_number VARCHAR(100),
    years_experience INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_caregivers_user_id ON caregivers(user_id);

CREATE TABLE patient_caregivers (
    assignment_id SERIAL PRIMARY KEY,
    patient_id INTEGER REFERENCES patients(patient_id) ON DELETE CASCADE,
    caregiver_id INTEGER REFERENCES caregivers(caregiver_id) ON DELETE CASCADE,
    relationship VARCHAR(50),  -- primary, backup, family, nurse, etc
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    notification_priority INTEGER DEFAULT 1,  -- 1 is the highest priority
    UNIQUE(patient_id, caregiver_id)
);

CREATE TABLE shift (
	shift_id SERIAL PRIMARY KEY,
    assignment_id INTEGER REFERENCES patient_caregivers(assignment_id) ON DELETE CASCADE,
    shift_type VARCHAR(20) NOT NULL CHECK (shift_type IN ('morning', 'afternoon', 'evening')),
    clock_in TIMESTAMP,
    clock_out TIMESTAMP,
	total_shift TIMESTAMP
);

CREATE INDEX idx_patient_caregivers_patient ON patient_caregivers(patient_id);
CREATE INDEX idx_patient_caregivers_caregiver ON patient_caregivers(caregiver_id);

-- fall detection

-- sensor data table for storing raw accel/gyro readings
CREATE TABLE sensor_data (
    data_id BIGSERIAL PRIMARY KEY,
    patient_id INTEGER REFERENCES patients(patient_id) ON DELETE CASCADE,
    sensor_type VARCHAR(50) NOT NULL,  -- accel, gyro
    device_id VARCHAR(100),
    value JSONB NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_sensor_patient ON sensor_data(patient_id);
CREATE INDEX idx_sensor_timestamp ON sensor_data(timestamp DESC);
CREATE INDEX idx_sensor_type ON sensor_data(sensor_type);

-- fall detection events
CREATE TABLE fall_detections (
    fall_id SERIAL PRIMARY KEY,
    patient_id INTEGER REFERENCES patients(patient_id) ON DELETE CASCADE,
    accelerometer_data JSONB,
    confidence_score DECIMAL(5, 4),
    false_alarm BOOLEAN,
    fall_location_lat DECIMAL(10, 8),
    fall_location_lng DECIMAL(11, 8),
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    response_time_seconds INTEGER,
    injury_reported BOOLEAN
);
 
CREATE INDEX idx_falls_patient ON fall_detections(patient_id);
CREATE INDEX idx_falls_timestamp ON fall_detections(timestamp DESC);

CREATE TABLE alerts (
    alert_id SERIAL PRIMARY KEY,
    event VARCHAR(100) NOT NULL,
    escalated BOOLEAN DEFAULT FALSE,
    from_device VARCHAR(100),
    room VARCHAR(100),
    video_url TEXT,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_alerts_timestamp ON alerts(timestamp DESC);
CREATE INDEX idx_alerts_event ON alerts(event);

CREATE TABLE patient_alerts (
    patient_alert_id SERIAL PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    alert_id INTEGER NOT NULL REFERENCES alerts(alert_id) ON DELETE CASCADE,
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMP,
    acknowledged_by INTEGER REFERENCES users(user_id),
    UNIQUE(patient_id, alert_id)
);

CREATE INDEX idx_patient_alerts_patient ON patient_alerts(patient_id);
CREATE INDEX idx_patient_alerts_alert ON patient_alerts(alert_id);
