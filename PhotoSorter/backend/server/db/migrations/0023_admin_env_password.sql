-- Keep the owner ID and leave other accounts untouched. Only the owner uses .env.
ALTER TABLE users ALTER COLUMN password_salt DROP NOT NULL;
ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;
UPDATE users SET password_salt=NULL, password_hash=NULL WHERE username='admin';
