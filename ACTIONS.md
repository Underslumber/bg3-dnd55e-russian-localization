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
  translation:update:
    intent: sync_ru_translation_with_upstream
    inputs:
      - Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml
      - glossary/glossary.normalized.json
      - AGENTS.md::Canonical Paths::Upstream English reference
    plan:
      - compare_en_vs_ru_by_keys
      - classify_diff_into_new_changed_stale_candidate
      - update_ru_for_new_and_changed_using_glossary
      - validate_xml_structure_and_service_attributes
      - prepare_delta_summary_counts
    checks:
      - xml_valid
      - glossary_consistency
      - scope_limited_to_localization_and_allowed_metadata
    outputs:
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

