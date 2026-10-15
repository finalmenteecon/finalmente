-- Finalmente · tabla del archivo de la cartelera
-- Pegar entero en Supabase > SQL Editor > New query > Run. Se puede correr más de una vez sin romper nada.

create table if not exists public.publicaciones (
  id           bigint generated always as identity primary key,
  huella       text not null unique,            -- identifica cada publicación tal como la escribió la Facultad
  codigo       text,                            -- MO245, TA236... (MO = optativa, el resto son tipos de ALE)
  titulo       text not null,
  tipo         text not null check (tipo in ('Optativa', 'ALE', 'Otro')),
  campos       jsonb not null default '{}'::jsonb,   -- docente, horario, cupo, inscripción, requisitos...
  html_crudo   text,                            -- la tarjeta original, por si cambia el diseño y hay que volver a leerla
  fuente       text not null,
  estado       text not null default 'publicada'
               check (estado in ('publicada', 'silenciosa', 'retenida')),
               -- publicada: se avisó por el canal
               -- silenciosa: se guardó en la primera corrida, sin avisar
               -- retenida: la frenó el freno de mano, no se avisó
  primera_vez  timestamptz not null default now()
);

create index if not exists publicaciones_codigo_idx on public.publicaciones (codigo);
create index if not exists publicaciones_primera_vez_idx on public.publicaciones (primera_vez desc);

-- Seguridad: con esto encendido y sin políticas, nadie puede leer ni escribir la tabla
-- salvo con la clave secreta, que solo tiene el bot. El sitio va a tener su propia regla de lectura.
alter table public.publicaciones enable row level security;
