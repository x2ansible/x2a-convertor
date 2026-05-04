# Configure HAProxy — main config and per-backend configs via loop.
class profile_haproxy::config {

  # Main configuration file from ERB template
  file { $profile_haproxy::config_file:
    ensure  => file,
    owner   => 'root',
    group   => $profile_haproxy::group,
    mode    => '0640',
    content => template('profile_haproxy/haproxy.cfg.erb'),
    notify  => Class['profile_haproxy::service'],
  }

  # Loop over backends hash to generate per-backend config fragments.
  # This is the key loop/map pattern — backends come from Hiera with deep merge
  # across multiple hierarchy levels.
  $profile_haproxy::backends.each |String $backend_name, Hash $backend_config| {
    $balance       = $backend_config['balance']
    $port          = $backend_config['port']
    $servers       = $backend_config['servers']
    $health_check  = $backend_config.dig('health_check')
    $health_interval = $backend_config.dig('health_interval')

    file { "${profile_haproxy::config_dir}/conf.d/${backend_name}.cfg":
      ensure  => file,
      owner   => 'root',
      group   => $profile_haproxy::group,
      mode    => '0640',
      content => epp('profile_haproxy/backend.conf.epp', {
        'backend_name'    => $backend_name,
        'balance'         => $balance,
        'port'            => $port,
        'servers'         => $servers,
        'health_check'    => $health_check,
        'health_interval' => $health_interval,
        'ssl_enabled'     => $profile_haproxy::ssl_enabled,
      }),
      notify  => Class['profile_haproxy::service'],
    }
  }

  # Deploy custom error pages
  ['503', '408'].each |String $code| {
    file { "${profile_haproxy::config_dir}/errors/${code}.http":
      ensure => file,
      source => "puppet:///modules/profile_haproxy/haproxy_errors/${code}.http",
      owner  => 'root',
      group  => $profile_haproxy::group,
      mode   => '0644',
    }
  }

  file { "${profile_haproxy::config_dir}/errors":
    ensure => directory,
    owner  => 'root',
    group  => $profile_haproxy::group,
    mode   => '0755',
    before => File["${profile_haproxy::config_dir}/errors/503.http"],
  }

  # Stick-table configuration (production only, set via Hiera)
  $stick_table_enabled = lookup('profile_haproxy::stick_table_enabled', Boolean, 'first', false)

  if $stick_table_enabled {
    $stick_table_size   = lookup('profile_haproxy::stick_table_size')
    $stick_table_expire = lookup('profile_haproxy::stick_table_expire')

    file { "${profile_haproxy::config_dir}/conf.d/stick-tables.cfg":
      ensure  => file,
      owner   => 'root',
      group   => $profile_haproxy::group,
      mode    => '0640',
      content => "# Managed by Puppet\nstick-table type ip size ${stick_table_size} expire ${stick_table_expire}\n",
      notify  => Class['profile_haproxy::service'],
    }
  }
}
