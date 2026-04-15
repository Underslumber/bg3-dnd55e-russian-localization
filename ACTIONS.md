# ACTIONS.md

VERSION: 3
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
  - prefer_existing_repo_scripts_over_manual_work: true

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
      - run_python_scripts/get-upstream-english.py_and_wait_until_output_exists
      - run_python_scripts/compare-translation.py_after_upstream_download_only
      - classify_diff_into_missing_changed_stale
      - write_machine_readable_and_markdown_reports_for_local_review
    checks:
      - xml_valid
      - cache_path_gitignored
      - local_only_no_ci_workflow_required
      - translation_steps_not_parallelized_when_file_dependency_exists
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
      - prepared_update_texts_for_updates_and_optional_adds
    plan:
      - create_temporary_copy_of_russian_xml
      - load_candidate_edit_file_and_temporary_xml
      - fail_if_add_entry_has_empty_text
      - apply_updates_and_optional_new_entries_by_contentuid
      - write_utf8_bom_xml_to_temporary_copy
      - validate_temporary_xml_via_separate_script
      - replace_original_russian_xml_after_successful_validation
      - report_changed_entries
    checks:
      - xml_valid
      - contentuid_uniqueness_preserved
      - only_requested_entries_changed
      - no_partial_replace_on_validation_failure
    outputs:
      - Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml
  translation:update:
    intent: sync_ru_translation_with_upstream
    inputs:
      - Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml
      - glossary/glossary.official.json
      - glossary/glossary.normalized.json
      - AGENTS.md::Canonical Paths::Upstream English reference
    plan:
      - run_translation:diff_sequentially
      - if_summary_has_no_missing_no_version_mismatch_no_stale_report_translation_up_to_date_and_stop
      - if_diff_exists_stop_after_generating_build/translation-diff/candidates.json_until_prepared_edits_are_provided_explicitly
      - review_build/translation-diff/candidates.json_before_apply
      - reuse_official_glossary_first_for_term_consistency_when_preparing_texts
      - use_normalized_glossary_only_as_secondary_fallback_without_overriding_official_terms
      - run_translation:apply_only_after_candidate_texts_are_filled_and_explicit_edits_path_is_passed
    checks:
      - xml_valid
      - glossary_consistency
      - scope_limited_to_localization_and_allowed_metadata
      - no_upstream_download_compare_race_condition
    outputs:
      - message: translation_up_to_date
      - build/translation-diff/summary.json
      - build/translation-diff/summary.md
      - build/translation-diff/candidates.json
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

