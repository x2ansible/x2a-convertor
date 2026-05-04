# Monitoring setup using virtual resources — only realized in production.
class profile_app_stack::monitoring {

  # Virtual resources — declared but not applied unless realized
  @package { 'prometheus-node-exporter':
    ensure => installed,
  }

  @service { 'prometheus-node-exporter':
    ensure  => running,
    enable  => true,
    require => Package['prometheus-node-exporter'],
  }

  @package { 'prometheus-pushgateway':
    ensure => installed,
  }

  @cron { 'push_app_metrics':
    command => "/usr/local/bin/app-healthcheck.sh --push-metrics",
    user    => $profile_app_stack::app_user,
    minute  => '*/5',
    require => [
      Package['prometheus-pushgateway'],
      File['/usr/local/bin/app-healthcheck.sh'],
    ],
  }

  # Realize monitoring resources only in production
  if $facts['environment'] == 'production' {
    realize Package['prometheus-node-exporter']
    realize Service['prometheus-node-exporter']
    realize Package['prometheus-pushgateway']
    realize Cron['push_app_metrics']
  }

  # Application health check (always active, regardless of environment)
  cron { 'app_health_check':
    command => "/usr/local/bin/app-healthcheck.sh http://localhost:${profile_app_stack::app_port}/health",
    user    => 'root',
    minute  => '*/2',
  }
}
