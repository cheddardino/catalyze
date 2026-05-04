-- Create users table with admin flag
create table if not exists public.users (
  id uuid primary key references auth.users (id) on delete cascade,
  email text unique not null,
  is_admin boolean default false,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now()
);

-- Create admin_logs table for audit trail
create table if not exists public.admin_logs (
  id bigserial primary key,
  admin_email text not null,
  action text not null, -- 'add_admin', 'remove_admin'
  target_email text not null,
  created_at timestamp with time zone default now()
);

-- Enable RLS
alter table public.users enable row level security;
alter table public.admin_logs enable row level security;

-- Users can read all users (for UI), but only insert their own
create policy "users_can_read_users" on public.users
  for select using (true);

-- Admins can update users
create policy "admins_can_update_users" on public.users
  for update using (
    exists (
      select 1 from public.users
      where id = auth.uid() and is_admin = true
    )
  );

-- Admin logs readable by admins only
create policy "admins_can_read_admin_logs" on public.admin_logs
  for select using (
    exists (
      select 1 from public.users
      where id = auth.uid() and is_admin = true
    )
  );

-- Insert initial admin: francisnaval13@gmail.com
insert into public.users (email, is_admin) 
values ('francisnaval13@gmail.com', true)
on conflict (email) do update
set is_admin = true;
