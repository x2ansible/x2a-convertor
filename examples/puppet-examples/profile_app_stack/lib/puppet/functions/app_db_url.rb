# Custom Puppet function to build a PostgreSQL connection URL.
# Used by profile_app_stack to construct DATABASE_URL from individual parameters.
Puppet::Functions.create_function(:'profile_app_stack::app_db_url') do
  dispatch :build_url do
    param 'String', :user
    param 'String', :password
    param 'String', :host
    param 'Integer', :port
    param 'String', :database
    return_type 'String'
  end

  def build_url(user, password, host, port, database)
    encoded_password = password.gsub('%', '%25')
                               .gsub('@', '%40')
                               .gsub(':', '%3A')
                               .gsub('/', '%2F')

    "postgresql://#{user}:#{encoded_password}@#{host}:#{port}/#{database}"
  end
end
