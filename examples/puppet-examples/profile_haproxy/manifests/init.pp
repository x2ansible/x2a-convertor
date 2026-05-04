# Main HAProxy profile class.
# Parameters are resolved via Hiera's 21-level hierarchy.
class profile_haproxy (
  String            $package_name    = lookup('profile_haproxy::package_name'),
  String            $config_dir      = lookup('profile_haproxy::config_dir'),
  String            $config_file     = lookup('profile_haproxy::config_file'),
  String            $service_name    = lookup('profile_haproxy::service_name'),
  String            $user            = lookup('profile_haproxy::user'),
  String            $group           = lookup('profile_haproxy::group'),
  Boolean           $stats_enabled   = lookup('profile_haproxy::stats_enabled'),
  Integer           $stats_port      = lookup('profile_haproxy::stats_port'),
  String            $stats_uri       = lookup('profile_haproxy::stats_uri'),
  String            $stats_user      = lookup('profile_haproxy::stats_user'),
  Sensitive[String] $stats_password  = Sensitive(lookup('profile_haproxy::stats_password')),
  Integer           $global_maxconn  = lookup('profile_haproxy::global_maxconn'),
  String            $client_timeout  = lookup('profile_haproxy::client_timeout'),
  String            $server_timeout  = lookup('profile_haproxy::server_timeout'),
  String            $connect_timeout = lookup('profile_haproxy::connect_timeout'),
  Integer           $retries         = lookup('profile_haproxy::retries'),
  Boolean           $ssl_enabled     = lookup('profile_haproxy::ssl_enabled'),
  String            $ssl_cert_path   = lookup('profile_haproxy::ssl_cert_path'),
  String            $ssl_key_path    = lookup('profile_haproxy::ssl_key_path'),
  String            $ssl_ciphers     = lookup('profile_haproxy::ssl_ciphers'),
  String            $ssl_min_version = lookup('profile_haproxy::ssl_min_version'),
  String            $log_server      = lookup('profile_haproxy::log_server'),
  String            $log_facility    = lookup('profile_haproxy::log_facility'),
  String            $log_level       = lookup('profile_haproxy::log_level'),
  Hash              $backends        = lookup('profile_haproxy::backends', { merge => 'deep' }),
) {

  contain profile_haproxy::install
  contain profile_haproxy::config
  contain profile_haproxy::service
  contain profile_haproxy::firewall

  Class['profile_haproxy::install']
  -> Class['profile_haproxy::config']
  ~> Class['profile_haproxy::service']
}
