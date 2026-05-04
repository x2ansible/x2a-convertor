# Manage HAProxy service lifecycle.
class profile_haproxy::service {

  service { $profile_haproxy::service_name:
    ensure     => running,
    enable     => true,
    hasrestart => true,
    hasstatus  => true,
    require    => Package[$profile_haproxy::package_name],
    subscribe  => File[$profile_haproxy::config_file],
  }

  # Validate config before restart
  exec { 'haproxy_config_check':
    command     => "haproxy -c -f ${profile_haproxy::config_file}",
    path        => ['/usr/sbin', '/usr/bin', '/sbin', '/bin'],
    refreshonly => true,
    subscribe   => File[$profile_haproxy::config_file],
    before      => Service[$profile_haproxy::service_name],
  }

  # Log rotation
  file { '/etc/logrotate.d/haproxy':
    ensure  => file,
    owner   => 'root',
    group   => 'root',
    mode    => '0644',
    content => @("EOF")
      /var/log/haproxy/*.log {
          daily
          rotate 14
          missingok
          notifempty
          compress
          delaycompress
          sharedscripts
          postrotate
              /bin/kill -HUP $(cat /var/run/haproxy.pid 2>/dev/null) 2>/dev/null || true
          endscript
      }
      | EOF
  }
}
