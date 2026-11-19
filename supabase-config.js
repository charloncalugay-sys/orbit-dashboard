/* ORBIT → Supabase connection (publishable key only — RPC + RLS enforce
   everything; same model as TEMPUS/VANGUARD). Loaded before orbit-auth-svc.js.
   Replace both values after creating the ORBIT Supabase project:
     Project URL  : https://<project-ref>.supabase.co
     Publishable  : sb_publishable_...                                  */
const SUPA = {
  URL: 'https://YOUR_PROJECT_REF.supabase.co',
  KEY: 'YOUR_PUBLISHABLE_KEY',
};
