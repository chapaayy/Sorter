-- Preserve all user IDs, password verifiers, ownership, quotas and explicit result grants.
CREATE TABLE account_roles (
 id TEXT PRIMARY KEY,
 name TEXT NOT NULL UNIQUE,
 description TEXT NOT NULL DEFAULT '',
 permissions JSONB NOT NULL DEFAULT '{}'::jsonb
);
INSERT INTO account_roles(id,name,description,permissions) VALUES
 ('owner','Владелец','Защищённый аккаунт владельца','{}'),
 ('administrator','Администратор','Просмотр и скачивание всех готовых результатов','{"results.view":"all","results.media":"all","results.zip":"all"}'),
 ('employee','Сотрудник','Просмотр и скачивание собственных готовых результатов','{"results.view":"own","results.media":"own","results.zip":"own"}'),
 ('observer','Наблюдатель','Доступ к явно выданным готовым отчётам','{"results.view":"granted","results.media":"granted","results.zip":"granted"}');
ALTER TABLE users ADD COLUMN role_id TEXT NOT NULL DEFAULT 'observer' REFERENCES account_roles(id) ON DELETE RESTRICT;
ALTER TABLE users ADD COLUMN display_name TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN blocked BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE users ADD COLUMN last_login_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN permission_overrides JSONB NOT NULL DEFAULT '{}'::jsonb;
UPDATE users SET role_id='owner' WHERE username='admin' AND access_role='owner';
ALTER TABLE users ADD CONSTRAINT protected_role_assignment CHECK(role_id<>'owner' OR (username='admin' AND access_role='owner'));
ALTER TABLE sessions ADD COLUMN session_id UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE;
ALTER TABLE sessions ADD COLUMN created_at TIMESTAMPTZ;
CREATE TABLE account_registration (
 singleton BOOLEAN PRIMARY KEY DEFAULT true CHECK(singleton),
 enabled BOOLEAN NOT NULL DEFAULT true
);
INSERT INTO account_registration(singleton) VALUES(true);
CREATE TABLE account_admin_events (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 at TIMESTAMPTZ NOT NULL DEFAULT now(),
 actor TEXT NOT NULL,
 target TEXT NOT NULL,
 action TEXT NOT NULL,
 detail JSONB NOT NULL DEFAULT '{}'::jsonb
);
