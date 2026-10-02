from .atlas_client import AtlasClient, AtlasAuthError, AtlasApiError
import logging

logger = logging.getLogger(__name__)

def ensure_ec2_ip_allowed(client: AtlasClient, ec2_public_ip: str, deployment_id: str = "") -> dict:
    """
    Ensure the EC2 public IP is in the Atlas project's network access list.
    Returns structured success/failure info.
    """
    try:
        # Validate IPv4 format roughly
        if not ec2_public_ip or ec2_public_ip.count(".") != 3:
            return {"status": "error", "message": "Invalid EC2 IP address"}
        
        # Only exactly the IP, no broader CIDR
        # Note: Atlas API expects raw IP address without /32 for single IPs usually,
        # but docs say either ipAddress or cidrBlock. The API allows CIDR blocks.
        # But adding an ipAddress automatically appends /32 conceptually.
        # Actually, if we send "34.229.19.143", Atlas accepts it.
        # If we send "34.229.19.143/32" as cidrBlock, that works too. 
        # We will use ipAddress.
        
        entries = client.get_network_access_list()
        
        # Check if IP exists
        for entry in entries:
            # Atlas might return cidrBlock like "34.229.19.143/32" or ipAddress "34.229.19.143"
            entry_ip = entry.get("ipAddress")
            entry_cidr = entry.get("cidrBlock")
            
            if entry_ip == ec2_public_ip or entry_cidr == f"{ec2_public_ip}/32":
                return {"status": "ATLAS_IP_ALREADY_ALLOWED", "message": f"IP {ec2_public_ip} already exists in Atlas access list"}

        # If not exists, add it
        comment = f"CloudWise deployment {deployment_id}" if deployment_id else "CloudWise deployment"
        client.add_network_access_entry(ec2_public_ip, comment=comment)
        
        return {"status": "ATLAS_IP_ADDED", "message": f"Added {ec2_public_ip}/32 to Atlas network access list"}
        
    except AtlasAuthError as e:
        logger.error(f"Atlas Auth Error: {e}")
        return {"status": "error", "message": str(e), "error_code": "ATLAS_AUTH_FAILED"}
    except AtlasApiError as e:
        logger.error(f"Atlas API Error: {e}")
        return {"status": "error", "message": str(e), "error_code": "ATLAS_API_FAILED"}
    except Exception as e:
        logger.exception("Unexpected error during Atlas IP allowlisting")
        return {"status": "error", "message": "Unexpected error", "error_code": "ATLAS_INTERNAL_ERROR"}
