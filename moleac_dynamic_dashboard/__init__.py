from . import models


def _fix_calendar_constraints(cr):
    """
    Change calendar_event FK constraints from RESTRICT to CASCADE so that
    Odoo's internal cleanup (ir.model reflection, demo-data teardown) can
    delete calendar.event records without hitting FK violations.
    """
    # ── calendar_event_res_partner_rel ────────────────────────────────
    cr.execute("""
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'calendar_event_res_partner_rel'
    """)
    if cr.fetchone():
        # Find the actual column that references calendar_event
        cr.execute("""
            SELECT kcu.column_name
            FROM   information_schema.table_constraints        tc
            JOIN   information_schema.key_column_usage         kcu
                   ON  kcu.constraint_name = tc.constraint_name
                   AND kcu.table_name      = tc.table_name
            JOIN   information_schema.referential_constraints  rc
                   ON  rc.constraint_name  = tc.constraint_name
            JOIN   information_schema.table_constraints        tc2
                   ON  tc2.constraint_name = rc.unique_constraint_name
            WHERE  tc.constraint_type = 'FOREIGN KEY'
            AND    tc.table_name      = 'calendar_event_res_partner_rel'
            AND    tc2.table_name     = 'calendar_event'
        """)
        row = cr.fetchone()
        event_col = row[0] if row else 'calendar_event_id'

        # Delete orphaned rows (only on the event FK column — safe regardless of partner col name)
        cr.execute(f"""
            DELETE FROM calendar_event_res_partner_rel
            WHERE  "{event_col}" NOT IN (SELECT id FROM calendar_event)
        """)

        # Re-create the FK as ON DELETE CASCADE
        cr.execute("""
            SELECT constraint_name
            FROM   information_schema.table_constraints
            WHERE  constraint_type = 'FOREIGN KEY'
            AND    table_name      = 'calendar_event_res_partner_rel'
            AND    constraint_name LIKE '%calendar_event_id%'
        """)
        for (cname,) in cr.fetchall():
            cr.execute(f"""
                ALTER TABLE calendar_event_res_partner_rel
                DROP CONSTRAINT IF EXISTS "{cname}"
            """)
        cr.execute(f"""
            ALTER TABLE calendar_event_res_partner_rel
            ADD  CONSTRAINT calendar_event_res_partner_rel_calendar_event_id_fkey
            FOREIGN KEY ("{event_col}") REFERENCES calendar_event(id)
            ON DELETE CASCADE
        """)

    # ── calendar_attendee ─────────────────────────────────────────────
    cr.execute("""
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'calendar_attendee'
    """)
    if cr.fetchone():
        cr.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name  = 'calendar_attendee'
            AND   column_name = 'event_id'
        """)
        if cr.fetchone():
            cr.execute("""
                DELETE FROM calendar_attendee
                WHERE event_id NOT IN (SELECT id FROM calendar_event)
            """)
            cr.execute("""
                ALTER TABLE calendar_attendee
                DROP CONSTRAINT IF EXISTS calendar_attendee_event_id_fkey
            """)
            cr.execute("""
                ALTER TABLE calendar_attendee
                ADD  CONSTRAINT calendar_attendee_event_id_fkey
                FOREIGN KEY (event_id) REFERENCES calendar_event(id)
                ON DELETE CASCADE
            """)


def pre_init_hook(env):
    _fix_calendar_constraints(env.cr)


def post_init_hook(env):
    _fix_calendar_constraints(env.cr)
