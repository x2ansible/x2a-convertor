# Application deployment — git clone, pip install, environment config.
class profile_app_stack::app {

  # Clone application repository
  vcsrepo { $profile_app_stack::app_dir:
    ensure   => latest,
    provider => git,
    source   => $profile_app_stack::app_repo,
    revision => $profile_app_stack::app_revision,
    user     => $profile_app_stack::app_user,
    require  => User[$profile_app_stack::app_user],
  }

  # Install Python requirements
  exec { 'install_requirements':
    command => "${profile_app_stack::app_dir}/venv/bin/pip install -r ${profile_app_stack::app_dir}/requirements.txt",
    cwd     => $profile_app_stack::app_dir,
    user    => $profile_app_stack::app_user,
    path    => ["${profile_app_stack::app_dir}/venv/bin", '/usr/bin', '/bin'],
    require => [Vcsrepo[$profile_app_stack::app_dir], Exec['create_app_venv']],
    unless  => "${profile_app_stack::app_dir}/venv/bin/pip freeze | diff - ${profile_app_stack::app_dir}/requirements.txt > /dev/null 2>&1",
    notify  => Class['profile_app_stack::service'],
  }

  # Install extra pip packages from Hiera
  $pip_packages = lookup('profile_app_stack::pip_packages', Array[String], 'first', [])

  if !empty($pip_packages) {
    $pip_packages.each |String $pkg| {
      exec { "install_pip_${pkg}":
        command => "${profile_app_stack::app_dir}/venv/bin/pip install ${pkg}",
        unless  => "${profile_app_stack::app_dir}/venv/bin/pip show ${pkg}",
        user    => $profile_app_stack::app_user,
        path    => ["${profile_app_stack::app_dir}/venv/bin", '/usr/bin', '/bin'],
        require => Exec['create_app_venv'],
      }
    }
  }

  # Environment file from template
  file { "${profile_app_stack::app_dir}/.env":
    ensure  => file,
    owner   => $profile_app_stack::app_user,
    group   => $profile_app_stack::app_group,
    mode    => '0600',
    content => template('profile_app_stack/app.env.erb'),
    notify  => Class['profile_app_stack::service'],
  }

  # Health check script
  file { '/usr/local/bin/app-healthcheck.sh':
    ensure => file,
    source => 'puppet:///modules/profile_app_stack/healthcheck.sh',
    owner  => 'root',
    group  => 'root',
    mode   => '0755',
  }

  # Database migrations
  exec { 'run_db_migrations':
    command     => "${profile_app_stack::app_dir}/venv/bin/python -m alembic upgrade head",
    cwd         => $profile_app_stack::app_dir,
    user        => $profile_app_stack::app_user,
    path        => ["${profile_app_stack::app_dir}/venv/bin", '/usr/bin', '/bin'],
    environment => ["DATABASE_URL=${profile_app_stack::db_url}"],
    refreshonly => true,
    subscribe   => Vcsrepo[$profile_app_stack::app_dir],
  }
}
