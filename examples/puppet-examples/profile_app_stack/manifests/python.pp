# Python runtime and virtualenv setup.
class profile_app_stack::python {

  $python_version = lookup('profile_app_stack::python_version')
  $pip_packages   = lookup('profile_app_stack::pip_packages', Array[String], 'first', [])

  # Install Python and development packages
  $python_packages = [
    $python_version,
    "${python_version}-pip",
    "${python_version}-venv",
    "${python_version}-dev",
    'git',
    'build-essential',
  ]

  package { $python_packages:
    ensure => installed,
  }

  # Application user and group
  group { $profile_app_stack::app_group:
    ensure => present,
    system => true,
  }

  user { $profile_app_stack::app_user:
    ensure     => present,
    gid        => $profile_app_stack::app_group,
    home       => $profile_app_stack::app_dir,
    shell      => '/bin/bash',
    system     => true,
    managehome => false,
    require    => Group[$profile_app_stack::app_group],
  }

  # Create application directory
  file { $profile_app_stack::app_dir:
    ensure => directory,
    owner  => $profile_app_stack::app_user,
    group  => $profile_app_stack::app_group,
    mode   => '0755',
  }

  # Create virtualenv
  exec { 'create_app_venv':
    command => "${python_version} -m venv ${profile_app_stack::app_dir}/venv",
    creates => "${profile_app_stack::app_dir}/venv/bin/activate",
    user    => $profile_app_stack::app_user,
    path    => ['/usr/bin', '/usr/local/bin', '/bin'],
    require => [Package[$python_packages], File[$profile_app_stack::app_dir]],
  }

  # Log directory
  file { $profile_app_stack::log_dir:
    ensure => directory,
    owner  => $profile_app_stack::app_user,
    group  => $profile_app_stack::app_group,
    mode   => '0755',
  }

  # Log rotation
  file { "/etc/logrotate.d/${profile_app_stack::app_name}":
    ensure  => file,
    owner   => 'root',
    group   => 'root',
    mode    => '0644',
    content => template('profile_app_stack/logrotate.conf.erb'),
  }
}
