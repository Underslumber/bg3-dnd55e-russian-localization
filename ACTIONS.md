# ACTIONS.md

VERSION: 2
MODE: machine-first
LANG: ru

ROUTING:
  - match_user_request_to_action_id: true
  - if_match: propose_action
  - if_no_match: ignore_actions_md
  - if_no_match_user_message: none

PROPOSE_RULE:
  - prompt_template: "Приступить к выполнению '{action_id}'?"
  - require_user_confirmation: true
  - execute_without_confirmation: false

EXECUTION_BASELINE:
  - enforce_agents_md: true
  - minimal_non_breaking_changes: true
  - steps_count_range: [3, 7]
  - before_commit_push: request_user_approval

REPORT_FORMAT:
  - done
  - changed_files
  - checks
  - remaining

ACTIONS:
  translation:diff:
    intent: fetch_upstream_english_and_compare_with_ru
    inputs:
      - AGENTS.md::Canonical Paths::Upstream English reference
      - Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml
    plan:
      - download_upstream_english_into_ignored_cache
      - compare_en_vs_ru_by_contentuid_and_version
      - classify_diff_into_missing_changed_stale
      - write_machine_readable_and_markdown_reports_for_local_review
    checks:
      - xml_valid
      - cache_path_gitignored
      - local_only_no_ci_workflow_required
    outputs:
      - .cache/upstream/english.xml
      - build/translation-diff/summary.json
      - build/translation-diff/summary.md
      - build/translation-diff/candidates.json
  translation:apply:
    intent: apply_translation_edits_to_russian_xml
    inputs:
      - Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml
      - build/translation-diff/candidates.json
      - external_edit_file_with_updates
    plan:
      - create_temporary_copy_of_russian_xml
      - load_edit_file_and_temporary_xml
      - apply_updates_and_optional_new_entries_by_contentuid
      - write_utf8_bom_xml_to_temporary_copy
      - validate_temporary_xml_via_separate_script
      - replace_original_russian_xml_after_successful_validation
      - report_changed_entries
    checks:
      - xml_valid
      - contentuid_uniqueness_preserved
      - only_requested_entries_changed
    outputs:
      - Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml
  translation:update:
    intent: sync_ru_translation_with_upstream
    inputs:
      - Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml
      - glossary/glossary.normalized.json
      - AGENTS.md::Canonical Paths::Upstream English reference
    plan:
      - refresh_upstream_english_cache
      - compare_en_vs_ru_by_contentuid_and_version
      - if_no_diff_report_translation_is_up_to_date_and_stop
      - else_apply_prepared_edits_to_temporary_russian_copy
      - validate_temporary_xml_via_separate_script
      - replace_original_russian_xml_after_successful_validation
    checks:
      - xml_valid
      - glossary_consistency
      - scope_limited_to_localization_and_allowed_metadata
    outputs:
      - message: translation_up_to_date
      - Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml
      - optional: Mods/DnD 5.5e AIO Russian/meta.lsx (release-only)
    after_success:
      - suggest_action: meta:sync-parent
        reason: "Обновить версию зависимости из родительского мода (актуальный Version64 и связанные поля зависимости)."

  action:report:
    intent: unified_task_report
    inputs:
      - task_context
      - modified_files
      - verification_results
    plan:
      - summarize_done
      - list_changed_files
      - list_checks
      - list_remaining
    checks:
      - concise
      - factual
      - no_unverified_claims
    outputs:
      - final_user_report
  meta:sync-parent:
    intent: sync_dependency_moduleshortdesc_from_parent_meta
    inputs:
      - parent_meta_git_url (optional; defaults to upstream)
      - Mods/DnD 5.5e AIO Russian/meta.lsx
    plan:
      - read_parent_moduleinfo_fields
      - validate_required_fields_folder_md5_name_publishhandle_uuid_version64
      - update_target_dependencies_moduleshortdesc_fields
      - validate_xml_structure
      - report_changed_fields
    checks:
      - xml_valid
      - required_parent_fields_present
      - only_dependencies_moduleshortdesc_changed
    outputs:
      - Mods/DnD 5.5e AIO Russian/meta.lsx

