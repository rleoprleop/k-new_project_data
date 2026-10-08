call audit.assert_zero(:'batch_id'::uuid,'reader_dw_schema_usage',$$
    select count(*)
    from (values
        ('role_operations_reader','dw_operations'),
        ('n8n_operations','dw_operations'),
        ('role_personalization_reader','dw_personalization'),
        ('n8n_personalization','dw_personalization')
    ) r(role_name,schema_name)
    where not has_schema_privilege(r.role_name,r.schema_name,'USAGE')
$$,'reader roles and logins must have usage on their own DW schema');

call audit.assert_zero(:'batch_id'::uuid,'reader_public_master_select',$$
    select count(*)
    from (values
        ('role_operations_reader','dw_operations'),
        ('n8n_operations','dw_operations'),
        ('role_personalization_reader','dw_personalization'),
        ('n8n_personalization','dw_personalization')
    ) r(role_name,schema_name)
    cross join unnest(array[
        'plans','age_benefits','plan_age_benefits','additional_services',
        'plan_benefits','discounts','internet_bundle_discount_rules',
        'premium_family_discount_rules'
    ]) t(table_name)
    where not has_table_privilege(
        r.role_name,format('%I.%I',r.schema_name,t.table_name),'SELECT')
$$,'reader roles and logins must select all eight public masters in their own DW');

call audit.assert_zero(:'batch_id'::uuid,'reader_private_table_select_denied',$$
    select count(*)
    from (values
        ('role_operations_reader','dw_operations'),
        ('n8n_operations','dw_operations'),
        ('role_personalization_reader','dw_personalization'),
        ('n8n_personalization','dw_personalization')
    ) r(role_name,schema_name)
    cross join pg_class c
    join pg_namespace n on n.oid=c.relnamespace
    where n.nspname in (
        'dw_operations','dw_personalization','dm_operations','dm_personalization')
      and c.relkind in ('r','p','v','m','f')
      and not (n.nspname=r.schema_name and c.relname in (
          'plans','age_benefits','plan_age_benefits','additional_services',
          'plan_benefits','discounts','internet_bundle_discount_rules',
          'premium_family_discount_rules'))
      and (has_table_privilege(r.role_name,c.oid,'SELECT')
          or has_any_column_privilege(r.role_name,c.oid,'SELECT'))
$$,'direct reads outside each reader public master allowlist must remain denied');

call audit.assert_zero(:'batch_id'::uuid,'reader_dw_dm_write_denied',$$
    select count(*)
    from unnest(array[
        'role_operations_reader','n8n_operations',
        'role_personalization_reader','n8n_personalization'
    ]) r(role_name)
    cross join pg_class c
    join pg_namespace n on n.oid=c.relnamespace
    where n.nspname in (
        'dw_operations','dw_personalization','dm_operations','dm_personalization')
      and c.relkind in ('r','p','v','m','f')
      and (has_table_privilege(
          r.role_name,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
          or has_any_column_privilege(r.role_name,c.oid,'INSERT,UPDATE,REFERENCES'))
$$,'reader roles and logins must not write to DW or DM objects');

call audit.assert_zero(:'batch_id'::uuid,'operations_preagg_view_reader_select',$$
    select count(*)
    from (values ('role_operations_reader'), ('n8n_operations')) r(role_name)
    where not has_schema_privilege(r.role_name,'ai_operations','USAGE')
       or not has_table_privilege(r.role_name,
           'ai_operations.v_customer_monthly_usage_filtered_preagg','SELECT')
$$,'operations readers must select the permanent customer/month preaggregation view');

call audit.assert_zero(:'batch_id'::uuid,'operations_preagg_view_column_contract',$$
    with expected_columns(position,column_name,data_type) as (
        values (1,'analysis_user_key','text'),(2,'calendar_month','date'),
               (3,'total_usage_mb','numeric'),(4,'month_key','integer')
    ), actual_columns as (
        select ordinal_position,column_name,data_type
        from information_schema.columns
        where table_schema='ai_operations'
          and table_name='v_customer_monthly_usage_filtered_preagg'
    ), differences as (
        (select * from expected_columns except select * from actual_columns)
        union all
        (select * from actual_columns except select * from expected_columns)
    )
    select count(*) from differences
$$,'preaggregation view must expose the four documented columns without a raw customer key');
