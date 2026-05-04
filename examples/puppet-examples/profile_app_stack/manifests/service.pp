# Systemd service management for the application.
class profile_app_stack::service {

  # Systemd unit file from EPP template
  file { "/etc/systemd/system/${profile_app_stack::app_name}.service":
    ensure  => file,
    owner   => 'root',
    group   => 'root',
    mode    => '0644',
    content => epp('profile_app_stack/app.service.epp', {
      'app_name'         => $profile_app_stack::app_name,
      'app_dir'          => $profile_app_stack::app_dir,
      'app_user'         => $profile_app_stack::app_user,
      'app_group'        => $profile_app_stack::app_group,
      'app_port'         => $profile_app_stack::app_port,
      'worker_count'     => $profile_app_stack::worker_count,
      'worker_class'     => $profile_app_stack::worker_class,
      'max_requests'     => $profile_app_stack::max_requests,
      'graceful_timeout' => $profile_app_stack::graceful_timeout,
      'log_dir'          => $profile_app_stack::log_dir,
      'log_level'        => $profile_app_stack::log_level,
    }),
    notify  => Exec['systemd_daemon_reload'],
  }

  exec { 'systemd_daemon_reload':
    command     => 'systemctl daemon-reload',
    path        => ['/usr/bin', '/bin'],
    refreshonly => true,
  }

  service { $profile_app_stack::app_name:
    ensure    => running,
    enable    => true,
    require   => [
      File["/etc/systemd/system/${profile_app_stack::app_name}.service"],
      Exec['systemd_daemon_reload'],
    ],
    subscribe => File["${profile_app_stack::app_dir}/.env"],
  }
}
