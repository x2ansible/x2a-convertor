# Install HAProxy and OS-specific dependencies.
class profile_haproxy::install {

  $extra_packages = lookup('profile_haproxy::extra_packages', Array[String], 'first', [])

  package { $profile_haproxy::package_name:
    ensure => installed,
  }

  if !empty($extra_packages) {
    package { $extra_packages:
      ensure  => installed,
      require => Package[$profile_haproxy::package_name],
    }
  }

  # Ensure haproxy user and group exist
  group { $profile_haproxy::group:
    ensure => present,
    system => true,
  }

  user { $profile_haproxy::user:
    ensure  => present,
    gid     => $profile_haproxy::group,
    home    => '/var/lib/haproxy',
    shell   => '/sbin/nologin',
    system  => true,
    require => Group[$profile_haproxy::group],
  }

  # Config and socket directories
  file { [$profile_haproxy::config_dir, "${profile_haproxy::config_dir}/conf.d"]:
    ensure => directory,
    owner  => 'root',
    group  => $profile_haproxy::group,
    mode   => '0755',
  }

  file { '/var/lib/haproxy':
    ensure => directory,
    owner  => $profile_haproxy::user,
    group  => $profile_haproxy::group,
    mode   => '0750',
  }

  # SELinux policy for HAProxy if on RHEL
  $selinux_enabled = lookup('profile_haproxy::selinux_enabled', Boolean, 'first', false)

  if $selinux_enabled {
    exec { 'haproxy_selinux_connect':
      command => 'setsebool -P haproxy_connect_any 1',
      unless  => 'getsebool haproxy_connect_any | grep -q on',
      path    => ['/usr/sbin', '/usr/bin', '/sbin', '/bin'],
      require => Package[$profile_haproxy::package_name],
    }
  }
}
