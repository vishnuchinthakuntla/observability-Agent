import React, { useEffect, useMemo, useState } from "react";
import "./users.css";
import { apiFetch } from '../../utils/apiClient';

interface User {
  id: string;
  username: string;
  email: string;
  is_active: boolean;
  created_at: string;
}

interface FormData {
  username: string;
  email: string;
  is_active: boolean;
}

const Users: React.FC = () => {
  const [loading, setLoading] = useState(true);

  const [users, setUsers] = useState<User[]>([]);

  const [search, setSearch] = useState("");

  const [showModal, setShowModal] = useState(false);

  const [selectedUser, setSelectedUser] =
    useState<User | null>(null);

  const [formData, setFormData] =
    useState<FormData>({
      username: "",
      email: "",
      is_active: true,
    });

  // ==========================
  // Fetch Users
  // ==========================

  const fetchUsers = async () => {
    try {
      setLoading(true);

      const apiBase = String(
        import.meta.env.VITE_API_BASE || ""
      ).replace(/\/+$/, "");

      const response = await apiFetch(
        `${apiBase}/custom-api/v1/users`
      );

      if (!response.ok) {
        throw new Error(`Failed to fetch users: ${response.status}`);
      }

      const data = await response.json();

      // Accept either an array or an object with `users` key
      const list = Array.isArray(data)
        ? data
        : data?.users || [];

      setUsers(list);
    } catch (error) {
      console.error(error);
      alert("Failed to load users");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  // ==========================
  // Search
  // ==========================

  const filteredUsers = useMemo(() => {
    return users.filter((user) => {
      const keyword = search.toLowerCase();

      return (
        user.username
          .toLowerCase()
          .includes(keyword) ||
        user.email
          .toLowerCase()
          .includes(keyword)
      );
    });
  }, [users, search]);

  // ==========================
  // Statistics
  // ==========================

  const totalUsers = users.length;

  const activeUsers = users.filter(
    (x) => x.is_active
  ).length;

  const inactiveUsers = users.filter(
    (x) => !x.is_active
  ).length;

  // ==========================
  // Open Edit Modal
  // ==========================

  const handleEdit = (user: User) => {
    setSelectedUser(user);

    setFormData({
      username: user.username,
      email: user.email,
      is_active: user.is_active,
    });

    setShowModal(true);
  };

  // ==========================
  // Update Form
  // ==========================

  const handleInputChange = (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const target = e.target as HTMLInputElement & {
      name: keyof FormData;
    };

    // Only handle text inputs (username/email) here
    if (target.name === "username" || target.name === "email") {
      setFormData((prev) => ({
        ...prev,
        [target.name]: target.value,
      }));
    }
  };

  const handleCheckbox = (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    setFormData((prev) => ({
      ...prev,
      is_active: e.target.checked,
    }));
  };

  // ==========================
  // Update User API
  // ==========================

  const updateUser = async () => {
    if (!selectedUser) return;

    try {
      const apiBase = String(
        import.meta.env.VITE_API_BASE || ""
      ).replace(/\/+$/, "");

      const response = await apiFetch(
        `${apiBase}/custom-api/v1/users/${selectedUser.id}`,
        {
          method: "PUT",
          headers: {
            "Content-Type":
              "application/json",
          },
          body: JSON.stringify({
            username:
              formData.username,
            email: formData.email,
            is_active:
              formData.is_active,
          }),
        }
      );

      if (!response.ok) {
        throw new Error(
          "Update Failed"
        );
      }

      alert(
        "User updated successfully."
      );

      setShowModal(false);
      setSelectedUser(null);

      fetchUsers();
    } catch (error) {
      console.error(error);

      alert(
        "Unable to update user."
      );
    }
  };

  // ==========================
  // Delete User
  // ==========================

  const deleteUser = async (
    id: string
  ) => {
    const confirmDelete =
      window.confirm(
        "Are you sure you want to delete this user?"
      );

    if (!confirmDelete) return;

    try {
      const apiBase = String(
        import.meta.env.VITE_API_BASE || ""
      ).replace(/\/+$/, "");

      const response = await apiFetch(
        `${apiBase}/custom-api/v1/users/${id}`,
        {
          method: "DELETE",
        }
      );

      if (!response.ok) {
        throw new Error(
          "Delete Failed"
        );
      }

      alert(
        "User deleted successfully."
      );

      fetchUsers();
    } catch (error) {
      console.error(error);

      alert(
        "Unable to delete user."
      );
    }
  };

  const formatDate = (iso?: string) => {
    if (!iso) return "-";
    const d = new Date(iso);
    return isNaN(d.getTime()) ? iso : d.toLocaleString();
  };

  return (
        <div className="users-page">
      {/* Header */}
      <div className="page-header">
        <h2>Users</h2>
        <p>Manage application users and their access.</p>
      </div>

      {/* Statistics */}
      <div className="stats-grid">
        <div className="stat-card">
          <span>Total Users</span>
          <h3>{totalUsers}</h3>
        </div>

        <div className="stat-card">
          <span>Active</span>
          <h3>{activeUsers}</h3>
        </div>

        <div className="stat-card">
          <span>Inactive</span>
          <h3>{inactiveUsers}</h3>
        </div>
      </div>

      {/* Search */}
      <div className="filter-card">
        <input
          className="search-box"
          type="search"
          placeholder="Search by username or email..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {/* Table */}

      <div className="table-container">
        {loading ? (
          <div className="loading">
            Loading Users...
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Username</th>
                <th>Email</th>
                <th>Status</th>
                <th>Created At</th>
                <th >
                  Actions
                </th>
              </tr>
            </thead>

            <tbody>
              {filteredUsers.length ===
              0 ? (
                <tr>
                  <td
                    colSpan={5}
                    className="empty"
                  >
                    No Users Found
                  </td>
                </tr>
              ) : (
                filteredUsers.map(
                  (user) => (
                    <tr key={user.id}>
                      <td>
                        {user.username}
                      </td>

                      <td>
                        {user.email}
                      </td>

                      <td>
                        <span
                          className={`status ${
                            user.is_active
                              ? "success"
                              : "error"
                          }`}
                        >
                          {user.is_active
                            ? "Active"
                            : "Inactive"}
                        </span>
                      </td>

                      <td>{formatDate(user.created_at)}</td>

                      <td>
                        <div className="action-buttons">
                          <button
                            className="edit-btn"
                            onClick={() =>
                              handleEdit(
                                user
                              )
                            }
                          >
                            Edit
                          </button>

                          <button
                            className="delete-btn"
                            onClick={() =>
                              deleteUser(
                                user.id
                              )
                            }
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                )
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Edit Modal */}

      {showModal && (
        <div className="modal-overlay">
          <div className="modal">
            <h3>Edit User</h3>

            <div className="form-group">
              <label htmlFor="username-input">Username</label>

              <input
                id="username-input"
                name="username"
                type="text"
                autoComplete="username"
                value={formData.username}
                onChange={handleInputChange}
              />
            </div>

            <div className="form-group">
              <label htmlFor="email-input">Email</label>

              <input
                id="email-input"
                name="email"
                type="email"
                autoComplete="email"
                value={formData.email}
                onChange={handleInputChange}
              />
            </div>

            <div className="checkbox-group">
              <input
                id="active"
                type="checkbox"
                checked={
                  formData.is_active
                }
                onChange={
                  handleCheckbox
                }
              />

              <label htmlFor="active">
                Active User
              </label>
            </div>

            <div className="modal-actions">
              <button
                className="save-btn"
                onClick={
                  updateUser
                }
              >
                Update
              </button>

              <button
                className="cancel-btn"
                onClick={() => {
                  setShowModal(false);
                  setSelectedUser(null);
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Users;