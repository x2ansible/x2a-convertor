Facter.add(:haproxy_version) do
  confine kernel: 'Linux'

  setcode do
    output = Facter::Core::Execution.execute('haproxy -v 2>/dev/null')
    if output && (match = output.match(/version\s+(\d+\.\d+\.\d+)/))
      match[1]
    else
      nil
    end
  end
end
