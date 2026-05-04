# Application stack orchestrator — strict dependency chain.
class profile_app_stack (
  String  $app_name        = lookup('profile_app_stack::app_name'),
  String  $app_repo        = lookup('profile_app_stack::app_repo'),
  String  $app_revision    = lookup('profile_app_stack::app_revision'),
  Integer $app_port        = lookup('profile_app_stack::app_port'),
  String  $app_dir         = lookup('profile_app_stack::app_dir'),
  String  $app_user        = lookup('profile_app_stack::app_user'),
  String  $app_group       = lookup('profile_app_stack::app_group'),
  String  $db_host         = lookup('profile_app_stack::db_host'),
  Integer $db_port         = lookup('profile_app_stack::db_port'),
  String  $db_name         = lookup('profile_app_stack::db_name'),
  String  $db_user         = lookup('profile_app_stack::db_user'),
  String  $db_password     = lookup('profile_app_stack::db_password'),
  Integer $worker_count    = lookup('profile_app_stack::worker_count'),
  String  $worker_class    = lookup('profile_app_stack::worker_class'),
  Integer $max_requests    = lookup('profile_app_stack::max_requests'),
  Integer $graceful_timeout = lookup('profile_app_stack::graceful_timeout'),
  String  $log_dir         = lookup('profile_app_stack::log_dir'),
  String  $log_level       = lookup('profile_app_stack::log_level'),
  String  $secret_key      = lookup('profile_app_stack::secret_key', default_value => 'changeme'),
) {

  # Build the database URL using a custom Puppet function
  $db_url = profile_app_stack::app_db_url(
    $db_user, $db_password, $db_host, $db_port, $db_name
  )

  contain profile_app_stack::python
  contain profile_app_stack::database
  contain profile_app_stack::app
  contain profile_app_stack::service
  contain profile_app_stack::monitoring

  # Strict dependency chain — each phase depends on the previous
  Class['profile_app_stack::python']
  -> Class['profile_app_stack::database']
  -> Class['profile_app_stack::app']
  ~> Class['profile_app_stack::service']
  -> Class['profile_app_stack::monitoring']
}
