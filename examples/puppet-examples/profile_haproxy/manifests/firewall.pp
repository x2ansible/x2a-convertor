# OS-conditional firewall configuration for HAProxy.
class profile_haproxy::firewall {

  $firewall_provider = lookup('profile_haproxy::firewall_provider', String, 'first', 'ufw')

  case $firewall_provider {
    'firewalld': {
      $firewall_zone = lookup('profile_haproxy::firewall_zone', String, 'first', 'public')

      # Open HTTP/HTTPS ports in firewalld
      ['80', '443'].each |String $port| {
        exec { "firewalld_allow_${port}":
          command => "firewall-cmd --zone=${firewall_zone} --add-port=${port}/tcp --permanent",
          unless  => "firewall-cmd --zone=${firewall_zone} --query-port=${port}/tcp",
          path    => ['/usr/bin', '/bin'],
          notify  => Exec['firewalld_reload'],
        }
      }

      if $profile_haproxy::stats_enabled {
        exec { "firewalld_allow_stats_${profile_haproxy::stats_port}":
          command => "firewall-cmd --zone=${firewall_zone} --add-port=${profile_haproxy::stats_port}/tcp --permanent",
          unless  => "firewall-cmd --zone=${firewall_zone} --query-port=${profile_haproxy::stats_port}/tcp",
          path    => ['/usr/bin', '/bin'],
          notify  => Exec['firewalld_reload'],
        }
      }

      exec { 'firewalld_reload':
        command     => 'firewall-cmd --reload',
        path        => ['/usr/bin', '/bin'],
        refreshonly => true,
      }
    }

    'ufw': {
      package { 'ufw':
        ensure => installed,
      }

      exec { 'ufw_allow_http':
        command => 'ufw allow 80/tcp',
        unless  => 'ufw status | grep -q "80/tcp.*ALLOW"',
        path    => ['/usr/sbin', '/usr/bin', '/sbin', '/bin'],
        require => Package['ufw'],
      }

      exec { 'ufw_allow_https':
        command => 'ufw allow 443/tcp',
        unless  => 'ufw status | grep -q "443/tcp.*ALLOW"',
        path    => ['/usr/sbin', '/usr/bin', '/sbin', '/bin'],
        require => Package['ufw'],
      }

      if $profile_haproxy::stats_enabled {
        exec { 'ufw_allow_stats':
          command => "ufw allow ${profile_haproxy::stats_port}/tcp",
          unless  => "ufw status | grep -q '${profile_haproxy::stats_port}/tcp.*ALLOW'",
          path    => ['/usr/sbin', '/usr/bin', '/sbin', '/bin'],
          require => Package['ufw'],
        }
      }

      exec { 'ufw_enable':
        command => 'ufw --force enable',
        unless  => 'ufw status | grep -q "Status: active"',
        path    => ['/usr/sbin', '/usr/bin', '/sbin', '/bin'],
        require => Package['ufw'],
      }
    }

    default: {
      notify { "Unknown firewall provider: ${firewall_provider}": }
    }
  }
}
